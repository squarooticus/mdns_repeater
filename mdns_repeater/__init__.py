import argparse
import logging

from .repeater import *

def main():
    parser = argparse.ArgumentParser(description='mDNS Repeater')

    parser.add_argument('repeat_ifaces', nargs='+', help='Interfaces to repeat between')
    parser.add_argument('-4', '--v4only', dest='v4only', action='store_true', help='Repeat over IPv4 only')
    parser.add_argument('-6', '--v6only', dest='v6only', action='store_true', help='Repeat over IPv6 only')
    parser.add_argument('--source4', dest='source4', default=[], nargs=2, action='append', help='For a given interface, use a specific source address for repeated IPv4 packets', metavar=('IFACE', 'ADDRESS'))
    parser.add_argument('--source6', dest='source6', default=[], nargs=2, action='append', help='For a given interface, use a specific source address for repeated IPv6 packets', metavar=('IFACE', 'ADDRESS'))
    parser.add_argument('-v', '--verbose', dest='verbose', default='WARNING', help='Logging verbosity (DEBUG, INFO, WARNING, ERROR, CRITICAL)')

    args = parser.parse_args()

    logging.basicConfig(encoding='utf-8', level=getattr(logging, args.verbose.upper()))

    repeat_ifs = args.repeat_ifaces
    logging.info(f"Repeating between interfaces: {' '.join(repeat_ifs)}")

    mdns_port = 5353

    try:
        if args.v6only:
            logging.info(f"Skipping IPv4")
        else:
            r_ipv4 = Repeater_IPv4("224.0.0.251", repeat_ifs, mdns_port, override_source_for_ifs=dict(args.source4))
            r_ipv4.start()

        if args.v4only:
            logging.info(f"Skipping IPv6")
        else:
            r_ipv6 = Repeater_IPv6("ff02::fb", repeat_ifs, mdns_port, override_source_for_ifs=dict(args.source6))
            r_ipv6.start()

        if not args.v6only: r_ipv4.join()
        if not args.v4only: r_ipv6.join()

    except KeyboardInterrupt:
        logging.info("Terminating")
