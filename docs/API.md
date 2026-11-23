# Python API reference

```python
from lgtvpy import LGTV
```

## Connecting

```python
tv = LGTV()                              # defaults to the TV you've paired
tv = LGTV("192.168.1.61", timeout=10.0)  # explicit IP

with LGTV() as tv:                       # recommended: auto connect + close
    ...
```

With no `ip`, the paired TV from `~/.lgtv/config.json` is used (works when exactly one TV is paired; otherwise pass the IP).

- `LGTV(ip=None, client_key=None, config_path=None, timeout=10.0, on_pair_prompt=None)`
  — `client_key` overrides the stored key; `on_pair_prompt` is a callback fired when the TV shows the pairing dialog.
- `tv.connect(pair_timeout=60)` — connect + authenticate explicitly. Optional: every method auto-connects on first use.
- `tv.close()` — close both sockets.

First-ever connection triggers the on-screen pairing prompt; the returned key is stored in `~/.lgtv/config.json` and reused automatically, together with the TV's MAC address for Wake-on-LAN.

Each connection first does the TV's pre-registration handshake (`hello`, then `getSystemInfo`, which webOS 25+ only answers before registration), then registers with LG's signed full-permission manifest. If the TV rejects that signature outright, it retries with an unsigned manifest. webOS 26 firmware does this ("403 Pairing rejected: blacklisted certificate detected"). Pairing then succeeds with reduced permissions, and `tv.signed_pairing` is `False`. A refused call raises `RequestError` with a note explaining why.

Errors raise `lgtvpy.LGTVError` (subclasses: `PairingError`, `RequestError`, `RequestTimeout`).

## Power

| Method | Description |
|---|---|
| `tv.power_off()` | Standby. |
| `tv.power_on(mac=None)` | Wake-on-LAN. Works while the TV is off; needs no connection. MAC auto-stored at pairing time. If only the wired + Wi-Fi pair could be discovered (webOS 26), both are stored and woken. |
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
| `tv.get_settings(category, keys=None)` | Read, e.g. `tv.get_settings("picture", ["backlight"])`. Only allow-listed keys are readable. |
| `tv.set_settings(category, {key: value}, current_app=None)` | Write any system setting (via the Luna bridge). Silent: the TV doesn't report bad keys/values. `truMotionMode`/`aspectRatio` are sent in their own write flagged `current_app` (the TV ignores them otherwise). Pass `current_app` to force the flag for the whole write. |
| `tv.set_system_settings(category, {key: value}, current_app=None)` | Write through the public settings API (webOS 24+). Raises `RequestError` on a rejected key/value, but only accepts a subset of keys. |
| `tv.get_picture_settings()` / `tv.set_picture_settings({...})` | Category `picture` shortcuts. |
| `tv.set_picture_mode("filmMaker")` | HDR/Dolby Vision content uses its own mode names (`hdrFilmMaker`, `dolbyHdrCinema`, …). |
| `tv.set_backlight(40)` | OLED light 0–100. |
| `tv.set_energy_saving("off")` | `off`, `auto`, `min`, `med`, `max`. On 2022+ firmware energy saving can lock the backlight, so turn it off first. |
| `tv.set_sound_mode("movie")` | `aiSoundPlus`, `standard`, `movie`, `news`, `sports`, `music`, `game`, `bassBlast`. |
| `tv.luna_request(uri, params)` | Escape hatch: call any `luna://` endpoint. |

Categories, keys and values: see [SETTINGS.md](SETTINGS.md).

## Profiles (TOML presets)

| Method | Description |
|---|---|
| `tv.apply_profile(path_or_dict, dry_run=False)` | Apply a whole TV state from a `.toml` file (or a parsed dict). Returns the list of steps taken. |
| `tv.capture_profile(name=None)` | Read the current input/volume/picture/sound into a profile dict. Picture captures every readable scalar key (`lgtvpy.tv.PICTURE_KEYS_EXTENDED`), falling back to the basic set on older firmware. |

The `lgtvpy.profiles` module has the underlying helpers: `load(path)`, `validate(profile)`, `plan(profile)` (human-readable steps, no TV needed), `apply(tv, profile, dry_run=False, settle=0.4)`, `capture(tv, name=None)`, and `dumps(profile)` (serialise back to TOML).

```python
from lgtvpy import LGTV, profiles

with LGTV() as tv:
    tv.apply_profile("profiles/game.toml")

    snapshot = tv.capture_profile(name="My look")
    with open("my_look.toml", "w", encoding="utf-8") as f:
        f.write(profiles.dumps(snapshot))
```

Profile schema and the two-phase picture-mode behaviour are documented in the module docstring and the README. When a `[picture]` table names `pictureMode` alongside other keys, the mode is applied first (in its own call) so it doesn't reload the preset's stored values over the ones you set — verified on webOS 25.

## Info & raw access

| Method | Description |
|---|---|
| `tv.system_info()` | Model name, serial, receiver type. On webOS 25+ the copy captured during the connection handshake is returned. |
| `tv.software_info()` | Firmware details; `device_id` = TV MAC address. Refused on webOS 26 (reduced-permission pairing). |
| `tv.connection_info()` | Wired and Wi-Fi MAC addresses. |
| `tv.hello_info()` | What the TV announced on connect: webOS version (`deviceOSReleaseVersion`), supported `pairingTypes`. |
| `tv.signed_pairing` | `False` if the TV only accepted the reduced-permission (unsigned) pairing. |
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
