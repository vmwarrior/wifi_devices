"""Active ARP-scan based device discovery.

Sends ARP requests to every address in the local subnet and collects the
replies. Requires root (raw sockets), so run via sudo or a root cron job.
"""

from __future__ import annotations

import socket
import subprocess

from db import Device


def detect_subnet(interface: str | None = None) -> tuple[str, str]:
    """Return (interface, subnet-in-CIDR) for the active connection.

    If no interface is given, the one carrying the default route is used.
    """
    if interface is None:
        route = subprocess.run(
            ["ip", "-o", "route", "get", "1.1.1.1"],
            capture_output=True, text=True, check=True,
        ).stdout
        # e.g. "1.1.1.1 via 192.168.0.1 dev wlan0 src 192.168.0.227 ..."
        parts = route.split()
        interface = parts[parts.index("dev") + 1]

    addr = subprocess.run(
        ["ip", "-o", "-f", "inet", "addr", "show", interface],
        capture_output=True, text=True, check=True,
    ).stdout
    # e.g. "3: wlan0    inet 192.168.0.227/24 brd ..."
    cidr = addr.split()[3]
    ip, prefix = cidr.split("/")
    octets = ip.split(".")
    # Assume a /24-style network for the scan range; adjust if needed.
    subnet = ".".join(octets[:3]) + ".0/" + prefix
    return interface, subnet


def _resolve_hostname(ip: str) -> str | None:
    try:
        return socket.gethostbyaddr(ip)[0]
    except (socket.herror, socket.gaierror, OSError):
        return None


def scan(subnet: str, timeout: int = 3) -> list[Device]:
    """ARP-scan the subnet and return the devices that replied."""
    # Imported lazily so that --list and friends work without root/scapy.
    from scapy.layers.l2 import ARP, Ether
    from scapy.sendrecv import srp

    try:
        from mac_vendor_lookup import MacLookup
        lookup = MacLookup()
    except Exception:
        lookup = None

    packet = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=subnet)
    answered, _ = srp(packet, timeout=timeout, verbose=0)

    devices: list[Device] = []
    for _sent, received in answered:
        mac = received.hwsrc.lower()
        ip = received.psrc
        vendor = None
        if lookup is not None:
            try:
                vendor = lookup.lookup(mac)
            except Exception:
                vendor = None
        devices.append(
            Device(mac=mac, ip=ip, hostname=_resolve_hostname(ip), vendor=vendor)
        )
    return devices
