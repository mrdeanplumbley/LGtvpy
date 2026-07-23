"""One-shot 'movie night' scene:

- Filmmaker picture mode, lower OLED light for a dark room
- Movie sound mode
- Comfortable volume
"""

from lgtvpy import LGTV

with LGTV() as tv:  # defaults to your paired TV
    tv.set_picture_mode("filmMaker")
    tv.set_picture_settings({"backlight": 35})
    tv.set_sound_mode("movie")
    tv.set_volume(14)
    tv.notify("Movie night mode enabled")
    print("Done. Current picture settings:")
    print(tv.get_picture_settings())
