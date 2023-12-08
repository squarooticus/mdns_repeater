import traceback
import socket

from socket import (
        AF_INET, AF_INET6,
        SOL_SOCKET, SO_REUSEADDR, SO_REUSEPORT,
        SOCK_DGRAM,
        IPPROTO_IP, IPPROTO_IPV6,
        IP_ADD_MEMBERSHIP,
        IPV6_PKTINFO, IPV6_RECVPKTINFO, IPV6_JOIN_GROUP,
        INADDR_ANY,
        inet_pton, inet_ntop,
        inet_aton, inet_ntoa,
        if_nametoindex,
        )

try:
        from socket import IP_PKTINFO
except ImportError:
        IP_PKTINFO = 8

import struct
from threading import Thread
import re
import logging
from abc import ABCMeta, abstractmethod
from .get_iface_addrs import get_iface_addrs

MAX_PKT_SIZE=9000

class NoLocalAddress(Exception): pass

iface_addrs = None
def one_addr_for_if_index(family, if_index):
    global iface_addrs
    if iface_addrs is None:
        iface_addrs = get_iface_addrs()
    for cand in iface_addrs[if_index]:
        if cand['family'] == family:
            if family == AF_INET6:
                if not re.match('fe80',cand['addr']): continue
            return cand['addr']
    raise NoLocalAddress()

class Repeater(Thread, metaclass=ABCMeta):
    def __init__(self, multicast_group, repeat_ifs, port, override_source_for_ifs={}):
        Thread.__init__(self, daemon=True)

        self.multicast_group = multicast_group
        self.repeat_ifis = [ if_nametoindex(iface) for iface in repeat_ifs ]
        self.port = port

        self.override_source = dict([ (if_nametoindex(iface), src_addr)
                                     for iface, src_addr in override_source_for_ifs.items() ])

        self.sock = socket.socket(self.family, SOCK_DGRAM)
        self.sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self.sock.setsockopt(SOL_SOCKET, SO_REUSEPORT, 1)
        self.enable_pktinfo()
        self.sock.bind(('', port))

        self.local_addrs = {}

        for if_index in self.repeat_ifis:
            self.join_group_on_if_index(if_index)
            logging.info(f"Joined group {self.multicast_group} on ifi {if_index}")
            self.local_addrs[if_index] = self.local_addr_for_if_index(if_index)
            logging.info(f"Using local address {self.local_addrs[if_index]} as source address when repeating to ifi {if_index}")

    def run(self):
        while True:
            data, ancdata, msgflags, addr = self.sock.recvmsg(MAX_PKT_SIZE, socket.CMSG_LEN(MAX_PKT_SIZE))
            logging.debug(f"Received message from {addr}, length {len(data)}, ancdata {ancdata}")
            rcvd_if_index, dst_addr = self.decode_ancdata(ancdata)
            logging.debug(f"over ifi {rcvd_if_index} with dest {dst_addr}")

            # Don't repeat anything that wasn't addressed to the multicast group, e.g., unicast
            if dst_addr != self.multicast_group:
                logging.debug(f"Not repeating message not addressed to group {self.multicast_group}")
                continue

            # Don't repeat something we sent on that interface
            if addr[0] == self.local_addrs[rcvd_if_index]:
                logging.debug(f"Not repeating message from ifi {rcvd_if_index} with local source {addr[0]}")
                continue

            # Repeat the message to other interfaces
            for if_index in self.repeat_ifis:

                # Don't repeat on the received interface
                if if_index == rcvd_if_index:
                    logging.debug(f"Not repeating back to ifi {if_index}")
                    continue

                try:
                    logging.debug(f"Repeating on ifi {if_index} to {self.multicast_group} with source {self.local_addrs[if_index]}")

                    self.sock.sendmsg([ data, ],
                                      self.encode_ancdata(if_index, self.local_addrs[if_index]),
                                      0, (self.multicast_group, self.port))
                except Exception as e:
                    logging.error(f"Error repeating to ifi {if_index}: {e}")
                    logging.debug(traceback.format_exc())

    def local_addr_for_if_index(self, if_index):
        return self.override_source.get(if_index, one_addr_for_if_index(self.family, if_index))

    @abstractmethod
    def enable_pktinfo(self): pass

    @abstractmethod
    def join_group_on_if_index(self, if_index): pass

    @classmethod
    @abstractmethod
    def decode_ancdata(cls, ancdata): pass

    @classmethod
    @abstractmethod
    def encode_ancdata(cls, if_index, local_addr): pass

class Repeater_IPv4(Repeater):
    def __init__(self, *args, **kwargs):
        self.family = AF_INET
        Repeater.__init__(self, *args, **kwargs)

    def enable_pktinfo(self):
        self.sock.setsockopt(IPPROTO_IP, IP_PKTINFO, 1)

    def join_group_on_if_index(self, if_index):
        self.sock.setsockopt(IPPROTO_IP, IP_ADD_MEMBERSHIP,
                                  struct.pack("4sII", inet_aton(self.multicast_group),
                                              INADDR_ANY, if_index))

    @classmethod
    def decode_ancdata(cls, ancdata):
        pktinfo_b = [ x[2] for x in ancdata if x[0] == IPPROTO_IP and x[1] == IP_PKTINFO ][0]
        if_index, local_addr, dst_addr = struct.unpack("I4s4s", pktinfo_b)
        return (if_index, inet_ntoa(dst_addr))

    @classmethod
    def encode_ancdata(cls, if_index, local_addr):
        return [ (IPPROTO_IP, IP_PKTINFO, struct.pack("I4s4s", if_index, inet_aton(local_addr), inet_aton("0.0.0.0"))) ]

class Repeater_IPv6(Repeater):
    def __init__(self, *args, **kwargs):
        self.family = AF_INET6
        Repeater.__init__(self, *args, **kwargs)

    def enable_pktinfo(self):
        self.sock.setsockopt(IPPROTO_IPV6, IPV6_RECVPKTINFO, 1)

    def join_group_on_if_index(self, if_index):
        self.sock.setsockopt(IPPROTO_IPV6, IPV6_JOIN_GROUP,
                                  struct.pack("16sI", inet_pton(AF_INET6, self.multicast_group),
                                              if_index))

    @classmethod
    def decode_ancdata(cls, ancdata):
        pktinfo_b = [ x[2] for x in ancdata if x[0] == IPPROTO_IPV6 and x[1] == IPV6_PKTINFO ][0]
        dst_addr, if_index = struct.unpack("16sI", pktinfo_b)
        return (if_index, inet_ntop(AF_INET6, dst_addr))

    @classmethod
    def encode_ancdata(cls, if_index, local_addr):
        return [ (IPPROTO_IPV6, IPV6_PKTINFO, struct.pack("16sI", inet_pton(AF_INET6, local_addr), if_index)) ]
