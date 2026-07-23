"""Switch the TV to a PC/console gaming setup and back.

Usage:
    python examples/pc_gaming.py on    # HDMI 2, game mode, bright
    python examples/pc_gaming.py off   # back to cinema defaults
"""

import sys

from lgtvpy import LGTV

mode = sys.argv[1] if len(sys.argv) > 1 else "on"

with LGTV() as tv:  # defaults to your paired TV
    if mode == "on":
        tv.set_input("HDMI_2")
        tv.set_picture_mode("game")
        tv.set_picture_settings({"backlight": 100})
        tv.set_sound_mode("game")
        tv.notify("Game mode on")
    else:
        tv.set_picture_mode("cinema")
        tv.set_picture_settings({"backlight": 50})
        tv.set_sound_mode("standard")
        tv.notify("Back to normal")
