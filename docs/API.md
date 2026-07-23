# Python API reference

```python
from lgtvpy import LGTV
```

## Connecting

```python
tv = LGTV()                              # defaults to 192.168.1.61
tv = LGTV("192.168.1.61", timeout=10.0)  # explicit

with LGTV() as tv:                       # recommended: auto connect + close
    ...
```

- `LGTV(ip=None, client_key=None, config_path=None, timeout=10.0, on_pair_prompt=None)`
  — `client_key` overrides the stored key; `on_pair_prompt` is a callback fired when the TV shows the pairing dialog.
- `tv.connect(pair_timeout=60)` — connect + authenticate explicitly. Optional: every method auto-connects on first use.
- `tv.close()` — close both sockets.

First-ever connection triggers the on-screen pairing prompt; the returned key is stored in `~/.lgtv/config.json` and reused automatically, together with the TV's MAC address for Wake-on-LAN.

Errors raise `lgtvpy.LGTVError` (subclasses: `PairingError`, `RequestError`, `RequestTimeout`).

## Power

| Method | Description |
|---|---|
| `tv.power_off()` | Standby. |
| `tv.power_on(mac=None)` | Wake-on-LAN. Works while the TV is off; needs no connection. MAC auto-stored at pairing time. |
| `tv.screen_off()` / `tv.screen_on()` | Panel off/on while apps and audio keep running. |
| `tv.power_state()` | `{'state': 'Active' | 'Screen Off' | ...}` |

## Volume & audio

| Method | Description |
|---|---|
| `tv.volume` | Current volume (property, `int`). |
| `tv.muted` | Current mute state (property, `bool`). |
| `tv.set_volume(level)` | 0–100. |
| `tv.volume_up()` / `tv.volume_down()` | Step. |
| `tv.set_mute(True/False)` / `tv.toggle_mute()` | |
| `tv.get_sound_output()` / `tv.set_sound_output(name)` | `tv_speaker`, `external_arc`, `bt_soundbar`, ... |
| `tv.get_volume()` | Raw payload from the TV. |

## Apps

| Method | Description |
|---|---|
| `tv.list_apps()` | `[{'id': 'netflix', 'title': 'Netflix', ...}, ...]` |
| `tv.current_app()` | Foreground app id, e.g. `com.webos.app.hdmi2`. |
| `tv.launch_app(app_id, params=None)` | e.g. `tv.launch_app("youtube.leanback.v4")`. `params` allows deep links (app-specific). |
| `tv.close_app(app_id)` | |
| `tv.open_url(url)` | Open in the TV browser. |

Common app ids: `netflix`, `youtube.leanback.v4`, `amazon`, `com.disney.disneyplus-prod`, `spotify-beehive`, `com.webos.app.hdmi1`…`hdmi4`, `com.webos.app.livetv`.

## Inputs & channels

| Method | Description |
|---|---|
| `tv.list_inputs()` | HDMI/external inputs with labels and connection state. |
| `tv.set_input("HDMI_1")` | Switch input. |
| `tv.channel_up()` / `tv.channel_down()` | |
| `tv.list_channels()` / `tv.current_channel()` | |
| `tv.set_channel("5")` | By number, or pass a channelId string. |

## Playback

`tv.play()`, `tv.pause()`, `tv.stop()`, `tv.rewind()`, `tv.fast_forward()` — controls whatever the foreground app is playing (app support varies).

## Remote buttons, pointer, text

| Method | Description |
|---|---|
| `tv.button(name, repeat=1)` | Press a remote button — names in `lgtvpy.BUTTONS` (`HOME`, `UP`, `ENTER`, `BACK`, `0`–`9`, ...). |
| `tv.click()` | Click at current pointer position. |
| `tv.move_pointer(dx, dy)` | Relative pointer move. |
| `tv.scroll(dy)` | Wheel scroll. |
| `tv.type_text("query")` | Types into whichever text field is focused on the TV. |
| `tv.delete_chars(n)` | Backspace × n. |
| `tv.send_enter()` | Enter/OK in the text field. |

## Notifications

`tv.notify("message")` — toast popup in the corner of the screen.

## Settings

| Method | Description |
|---|---|
| `tv.get_settings(category, keys=None)` | Read, e.g. `tv.get_settings("picture", ["backlight"])`. |
| `tv.set_settings(category, {key: value})` | Write any system setting (via the Luna bridge). |
| `tv.get_picture_settings()` / `tv.set_picture_settings({...})` | Category `picture` shortcuts. |
| `tv.set_picture_mode("filmMaker")` | |
| `tv.set_backlight(40)` | OLED light 0–100. |
| `tv.set_energy_saving("off")` | On 2022+ firmware energy saving can lock the backlight — turn it off first. |
| `tv.set_sound_mode("movie")` | |
| `tv.luna_request(uri, params)` | Escape hatch: call any `luna://` endpoint. |

Categories, keys and values: see [SETTINGS.md](SETTINGS.md).

## Info & raw access

| Method | Description |
|---|---|
| `tv.system_info()` | Model name, firmware branch. |
| `tv.software_info()` | Firmware details; `device_id` = TV MAC address. |
| `tv.status()` | One-call summary (power/app/volume/mute/output). |
| `tv.request(uri, payload=None)` | Any raw `ssap://` request. |

## Subscriptions (advanced)

The low-level client can subscribe to state changes:

```python
with LGTV() as tv:
    sub_id, current = tv.client.subscribe("ssap://audio/getVolume")
    print("now:", current)
    for event_id, payload in tv.client.events(timeout=60):
        print("update:", payload)   # fires on every volume change
```

Useful subscription URIs: `ssap://audio/getVolume`,
`ssap://com.webos.applicationManager/getForegroundAppInfo`,
`ssap://com.webos.service.tvpower/power/getPowerState`,
`ssap://tv/getCurrentChannel`.
