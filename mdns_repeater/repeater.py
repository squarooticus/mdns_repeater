import socket

from socket import (
        AF_INET, AF_INET6,
        SOL_SOCKET, SO_REUSEADDR, SO_REUSEPORT,
        SOCK_DGRAM,
        IPPROTO_IP, IPPROTO_IPV6,
        IP_ADD_MEMBERSHIP,
        IPV6_PKTINFO, IPV6_RECVPKTINFO, IPV6_JOIN_GROUP,
        INADDR_ANY,
        inet_ntop, inet_pton, inet_aton,
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
    def __init__(self, multicast_group, repeat_ifs, port):
        Thread.__init__(self, daemon=True)

        self.multicast_group = multicast_group
        self.repeat_ifis = [ if_nametoindex(iface) for iface in repeat_ifs ]
        self.port = port

        self.recv_sock = socket.socket(self.family, SOCK_DGRAM)
        self.recv_sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        self.recv_sock.setsockopt(SOL_SOCKET, SO_REUSEPORT, 1)
        self.enable_pktinfo()
        self.recv_sock.bind(('', port))

        self.send_socks = {}
        self.local_addrs = {}

        for if_index in self.repeat_ifis:
            self.join_group_on_if_index(if_index)

            self.local_addrs[if_index] = self.bind_addr_for_if_index(if_index)

            send_sock = socket.socket(self.family, SOCK_DGRAM)
            send_sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
            send_sock.setsockopt(SOL_SOCKET, SO_REUSEPORT, 1)
            send_sock.bind(self.local_addrs[if_index])
            self.send_socks[if_index] = send_sock

    def run(self):
        while True:
            data, ancdata, msgflags, addr = self.recv_sock.recvmsg(MAX_PKT_SIZE, socket.CMSG_LEN(MAX_PKT_SIZE))
            logging.debug(f"Received message from {addr[0]}, length {len(data)}")
            rcvd_if_index = self.get_ancdata_if_index(ancdata)
            logging.debug(f"from ifi {rcvd_if_index}")

            # Don't repeat something we sent on that interface
            if addr[0] == self.local_addrs[rcvd_if_index][0]:
                logging.debug(f"Not repeating message from ifi {rcvd_if_index} with local source {addr[0]}")
                continue

            # Repeat the message to other interfaces
            for if_index, send_sock in self.send_socks.items():

                # First, discard any accumulated packets. We don't care about
                # any packets unicast to us since we are not an mDNS client.
                try:
                    while True:
                        send_sock.recvfrom(MAX_PKT_SIZE, socket.MSG_DONTWAIT)
                        logging.debug(f"Discarded inbound packet to {self.local_addrs[if_index][0]}")
                except BlockingIOError:
                    pass

                # Don't repeat on the received interface
                if if_index == rcvd_if_index:
                    logging.debug(f"Not repeating back to ifi {if_index}")
                    continue

                try:
                    logging.debug(f"Repeating to ifi {if_index} with source {self.local_addrs[if_index][0]}")
                    send_sock.sendto(data, (self.multicast_group, self.port))
                except Exception as e:
                    logging.error(f"Error repeating to ifi {if_index}: {e}")

    @abstractmethod
    def enable_pktinfo(self): pass

    @abstractmethod
    def join_group_on_if_index(self, if_index): pass

    @abstractmethod
    def bind_addr_for_if_index(self, if_index): pass

    @abstractmethod
    def get_ancdata_if_index(self, ancdata): pass

class Repeater_IPv4(Repeater):
    def __init__(self, *args, **kwargs):
        self.family = AF_INET
        Repeater.__init__(self, *args, **kwargs)

    def enable_pktinfo(self):
        self.recv_sock.setsockopt(IPPROTO_IP, IP_PKTINFO, 1)

    def join_group_on_if_index(self, if_index):
        self.recv_sock.setsockopt(IPPROTO_IP, IP_ADD_MEMBERSHIP,
                                  struct.pack("4sII", inet_aton(self.multicast_group),
                                              INADDR_ANY, if_index))

    def bind_addr_for_if_index(self, if_index):
        return (one_addr_for_if_index(self.family, if_index), self.port)

    def get_ancdata_if_index(self, ancdata):
        pktinfo_b = [ x[2] for x in ancdata if x[0] == IPPROTO_IP and x[1] == IP_PKTINFO ][0]
        if_index, local_addr_b, dst_addr_b = struct.unpack("I4s4s", pktinfo_b)
        return if_index

class Repeater_IPv6(Repeater):
    def __init__(self, *args, **kwargs):
        self.family = AF_INET6
        Repeater.__init__(self, *args, **kwargs)

    def enable_pktinfo(self):
        self.recv_sock.setsockopt(IPPROTO_IPV6, IPV6_RECVPKTINFO, 1)

    def join_group_on_if_index(self, if_index):
        self.recv_sock.setsockopt(IPPROTO_IPV6, IPV6_JOIN_GROUP,
                                  struct.pack("16sI", inet_pton(AF_INET6, self.multicast_group),
                                              if_index))

    def bind_addr_for_if_index(self, if_index):
        return (one_addr_for_if_index(self.family, if_index), self.port, 0, if_index)

    def get_ancdata_if_index(self, ancdata):
        pktinfo_b = [ x[2] for x in ancdata if x[0] == IPPROTO_IPV6 and x[1] == IPV6_PKTINFO ][0]
        dst_addr_b, if_index = struct.unpack("16sI", pktinfo_b)
        return if_index
