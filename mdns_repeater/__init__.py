import argparse
import logging

from .repeater import *

def main():
    parser = argparse.ArgumentParser(description='mDNS Repeater')

    parser.add_argument('repeat_ifaces', nargs='+', help='Interfaces to repeat between')
    parser.add_argument('-4', dest='v4only', action='store_true', help='Repeat over IPv4 only')
    parser.add_argument('-6', dest='v6only', action='store_true', help='Repeat over IPv6 only')
    parser.add_argument('-v', '--verbose', dest='verbose', default='WARNING', help='Logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL)')

    args = parser.parse_args()

    logging.basicConfig(encoding='utf-8', level=getattr(logging, args.verbose.upper()))

    repeat_ifs = args.repeat_ifaces
    logging.info(f"Repeating between interfaces: {' '.join(repeat_ifs)}")

    iface_addrs = get_iface_addrs()

    mdns_port = 5353

    try:
        if args.v6only:
            logging.info(f"Skipping IPv4")
        else:
            r_ipv4 = Repeater_IPv4("224.0.0.251", repeat_ifs, mdns_port)
            r_ipv4.start()

        if args.v4only:
            logging.info(f"Skipping IPv6")
        else:
            r_ipv6 = Repeater_IPv6("ff02::fb", repeat_ifs, mdns_port)
            r_ipv6.start()

        if not args.v6only: r_ipv4.join()
        if not args.v4only: r_ipv6.join()

    except KeyboardInterrupt:
        logging.info("Terminating")
