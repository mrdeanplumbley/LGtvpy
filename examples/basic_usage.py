"""Minimal example: connect, show status, say hello.

First run triggers the pairing prompt on the TV - accept it with the remote.
"""

from lgtvpy import LGTV

with LGTV("192.168.1.61") as tv:
    print("Status:", tv.status())
    tv.notify("Hello from Python!")
