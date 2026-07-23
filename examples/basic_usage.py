"""Minimal example: connect, show status, say hello.

First run triggers the pairing prompt on the TV - accept it with the remote.
"""

from lgtvpy import LGTV

# LGTV() defaults to the TV you've paired; pass an IP to override,
# e.g. LGTV("192.168.1.61").
with LGTV() as tv:
    print("Status:", tv.status())
    tv.notify("Hello from Python!")
