# mDNS Repeater

The entire purpose of this project is to repeat mDNS packets verbatim across VLANs because Google casting appears to be unhappy with whatever processing avahi-daemon does on the speaker group advertisements sent by Google speakers. (I am 99% sure this is Google's fault, but I haven't been motivated to track down what they're doing.)

This fairly simple multicast DNS repeater replaces a janky nftables configuration that I was never really happy with. What it does is very simple: it listens on port 5353 of multicast groups 224.0.0.251 and ff02::fb on the specified interfaces, and repeats incoming packets from each to the others on the same port and group with the source address replaced by an address configured on the outgoing interface, taking care not to re-repeat packets it is responsible for having sent.

For IPv4, the source address is set to an arbitrary IPv4 address from the sending interface. For IPv6, the source address is set to an arbitrary link-local IPv6 address (i.e., from fe80::/16) from the sending interface.

## systemd

The systemd configuration assumes:

- You have created a user called `mdnsrptr` with a home directory `/home/mdnsrptr`.
- You have created `/etc/default/mdns_repeater` with an appropriate value for `REPEAT_IFACES`.
- You have cloned the repo into that home directory and used `pipx` to install the repo into `~/.local`.

You'll want to copy the systemd configuration into `/etc/systemd/system` and then enable and start the service.

## Licensing

MIT. See `LICENSE` in the repo for details. Note that I am not sure what the licensing of `get_iface_addrs.py` is given its provenance (q.v., the [source repo](https://github.com/Torxed/Scripts/blob/master/python/get_network_interfaces.py)), so this license may not apply to that file.
