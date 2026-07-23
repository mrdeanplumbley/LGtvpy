"""LGtvpy - Control LG webOS TVs (e.g. OLED42C34LA) from your PC.

Quick start::

    from lgtvpy import LGTV

    with LGTV() as tv:  # defaults to your paired TV; or LGTV("192.168.1.61")
        tv.set_volume(15)
        tv.notify("Hello from Python!")
"""

from . import profiles
from .client import (
    LGTVError,
    PairingError,
    RequestError,
    RequestTimeout,
    WebOSClient,
)
from .keys import BUTTONS
from .tv import LGTV
from .wol import send_magic_packet

__version__ = "1.0.0"

__all__ = [
    "LGTV",
    "WebOSClient",
    "LGTVError",
    "PairingError",
    "RequestError",
    "RequestTimeout",
    "BUTTONS",
    "send_magic_packet",
    "profiles",
]
