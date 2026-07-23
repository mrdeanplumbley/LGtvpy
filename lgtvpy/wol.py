"""Wake-on-LAN - the only way to power the TV on when it is in standby."""

from __future__ import annotations

import re
import socket

_MAC_RE = re.compile(r"^[0-9a-fA-F]{2}([:\-]?[0-9a-fA-F]{2}){5}$")


def send_magic_packet(mac: str, broadcast: str = "255.255.255.255") -> None:
    """Send a WoL magic packet to ``mac`` (format ``aa:bb:cc:dd:ee:ff``).

    The TV must have "Turn On via Wi-Fi" / Quick Start+ enabled for this to
    work (see README - Powering the TV on).
    """
    if not _MAC_RE.match(mac):
        raise ValueError(f"Invalid MAC address: {mac!r}")
    mac_bytes = bytes.fromhex(mac.replace(":", "").replace("-", ""))
    packet = b"\xff" * 6 + mac_bytes * 16
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        for port in (9, 7):  # both common WoL ports, for good measure
            sock.sendto(packet, (broadcast, port))
