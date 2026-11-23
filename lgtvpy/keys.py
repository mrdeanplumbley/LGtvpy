"""Remote-control button names accepted by the pointer input socket.

Use with :meth:`lgtvpy.tv.LGTV.button`, e.g. ``tv.button("HOME")``.
Compiled from the button sets Home Assistant (aiowebostv) and bscpylgtv
maintain for current webOS TVs. Not every model has every button; the TV
silently ignores names it doesn't know. Factory service-menu keys
(EZ_ADJUST, IN_START) are deliberately left out.
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
    "HOME",           # Home dashboard
    "MENU",           # Quick settings
    "QMENU",          # Quick settings
    "INFO",
    "GUIDE",
    "PROGRAM",        # TV guide
    "LIST",           # Live TV channel list
    "DASH",           # "-" separator on the number pad
    "ASTERISK",
    "POWER",          # standby (can't wake the TV - use `lgtv on`)
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
    "RECLIST",        # recordings list
    # Colour buttons
    "RED",
    "GREEN",
    "YELLOW",
    "BLUE",
    # Panels & shortcuts
    "INPUT_HUB",      # input / home hub
    "MYAPPS",
    "RECENT",         # recent apps
    "SEARCH",
    "SCREEN_REMOTE",  # "more actions" panel
    "ASPECT_RATIO",
    "EZPIC",          # picture-mode panel
    "EYE_Q",          # energy-saving panel
    "TIMER",          # sleep timer panel
    "MAGNIFIER_ZOOM",
    "LIVE_ZOOM",
    "EMANUAL",        # user guide
    "NETFLIX",
    "AMAZON",
    "TV",
    "3D_MODE",        # 3D-capable models only
    # Accessibility / teletext
    "CC",             # closed captions / subtitles
    "AD",             # audio description
    "SAP",            # multi-audio
    "TELETEXT",
    "TEXTOPTION",
]
