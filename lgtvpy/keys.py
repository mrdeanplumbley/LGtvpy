"""Remote-control button names accepted by the pointer input socket.

Use with :meth:`lgtvpy.tv.LGTV.button`, e.g. ``tv.button("HOME")``.
This list covers the buttons known to work on modern webOS TVs (C-series
OLEDs included); some models accept additional names.
"""

BUTTONS = [
    # Navigation
    "UP",
    "DOWN",
    "LEFT",
    "RIGHT",
    "ENTER",
    "BACK",
    "EXIT",
    "HOME",
    "MENU",       # opens quick settings
    "INFO",
    "GUIDE",
    "DASH",       # "-" separator on the number pad
    "ASTERISK",
    # Numbers
    "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
    # Volume / channel (also available as dedicated SSAP calls)
    "VOLUMEUP",
    "VOLUMEDOWN",
    "MUTE",
    "CHANNELUP",
    "CHANNELDOWN",
    # Playback
    "PLAY",
    "PAUSE",
    "STOP",
    "REWIND",
    "FASTFORWARD",
    "RECORD",
    # Colour buttons
    "RED",
    "GREEN",
    "YELLOW",
    "BLUE",
    # Misc
    "CC",         # closed captions / subtitles
    "AD",         # audio description
]
