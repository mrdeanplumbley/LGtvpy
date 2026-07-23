# LGtvpy

Control your LG webOS TV from your PC over the local network — power, volume, inputs, apps, channels, remote buttons, text entry, notifications, and **every picture / sound / system setting** via the settings service.

Works with any recent LG webOS TV (developed and tested against a C3 OLED on webOS 25). Ships as a Python library (`lgtvpy`) **and** a command-line tool (`lgtv ...`). After a one-time pairing, the tool remembers your TV, so everyday commands need no arguments.

## How it works

LG webOS TVs expose a WebSocket control API ("SSAP") on the TV itself — no cloud, no LG account. This tool connects to `wss://<tv-ip>:3001`, pairs once (you accept a prompt on the TV), then sends JSON commands. Settings that the public API can't write (picture mode, OLED light, etc.) are changed through the TV's internal Luna settings service using a well-established bridge technique — the same one Home Assistant's community tooling uses.

## Setup

Requires Python 3.9+ and your PC on the same network as the TV.

```bash
pip install -e .
```

This installs the one dependency (`websocket-client`) and gives you the `lgtv` command. Alternatively `pip install -r requirements.txt` and use `python -m lgtvpy` instead of `lgtv`.

> **`lgtv` not recognized?** Your Python `Scripts` folder isn't on PATH. Either add it (below), or just use `python -m lgtvpy ...` — identical behaviour.

#### Adding Scripts to PATH - Windows Powershell
```powershell
$dir = py -c "import sysconfig; print(sysconfig.get_path('scripts','nt_user'))"
$old = [Environment]::GetEnvironmentVariable('Path','User')
if ($old -notlike "*$dir*") {
    [Environment]::SetEnvironmentVariable('Path', ($old.TrimEnd(';') + ';' + $dir), 'User')
}
$env:Path += ";$dir"
```

#### Adding Scripts to PATH - Linux
```bash
dir="$(python3 -m site --user-base)/bin"
case ":$PATH:" in
  *":$dir:"*) ;;
  *) echo "export PATH=\"\$PATH:$dir\"" >> ~/.bashrc ;;
esac
export PATH="$PATH:$dir"
```

### First-time pairing

1. Turn the TV on and find its IP address (*TV Settings → Network → Wi-Fi/Wired Connection → Advanced*, or your router's device list — giving the TV a static/reserved IP is recommended).
2. Run:

```bash
lgtv pair --ip 192.168.1.61        # use YOUR TV's IP
```

3. A prompt appears on the TV — select **Accept** with the remote.

That's it. The pairing key (and the TV's MAC address, needed for power-on) is saved to `~/.lgtv/config.json`, and from now on **`--ip` is optional**: with one TV paired, every command targets it automatically. Commands also pair automatically on first use, `pair` just does it explicitly.

Got several TVs? Pair each one, then pass `--ip <address>` (or `LGTV("<address>")` in Python) to pick one.

### Powering the TV **on** works via Wake-on-LAN

The TV can't be reached over the network while in standby, so `lgtv on` sends a Wake-on-LAN magic packet instead. For this to work, enable on the TV:

> **Settings → General → Devices → TV Management → Turn On via Wi-Fi** (name/location varies slightly by firmware; sometimes tied to *Quick Start+*)

Everything else (including `off`) uses the live connection.

## CLI usage

### Power

```bash
lgtv on               # wake via Wake-on-LAN
lgtv off              # standby
lgtv screen-off       # panel off, audio/apps keep running (great for music)
lgtv screen-on
lgtv status           # power state, current app, volume, mute, sound output
```

### Volume & audio

```bash
lgtv vol              # show volume + mute state
lgtv vol 15           # set volume 0-100
lgtv vol up           # step up
lgtv vol down         # step down
lgtv mute             # toggle
lgtv mute on          # or explicit on/off
lgtv sound-output                  # show current output
lgtv sound-output external_arc     # switch to eARC/soundbar
lgtv sound-output tv_speaker       # back to TV speakers
```

### Inputs & apps

```bash
lgtv inputs                        # list HDMI inputs with labels
lgtv input HDMI_1                  # switch input
lgtv apps                          # list installed apps (id + title)
lgtv app                           # what's in the foreground
lgtv launch netflix
lgtv launch youtube.leanback.v4
lgtv close netflix
lgtv open https://example.com      # TV web browser
```

### Picture & sound settings

```bash
lgtv picture-mode filmMaker        # cinema, game, vivid, expert1, ...
lgtv backlight 40                  # OLED light 0-100
lgtv energy-saving off             # off, min, med, max, auto
lgtv sound-mode movie              # aiSoundPlus, standard, movie, ...

# Generic access to ANY setting:
lgtv settings get picture                          # common picture settings
lgtv settings get picture contrast color           # specific keys
lgtv settings set picture contrast 85
lgtv settings set sound soundMode movie
lgtv settings set picture pictureMode expert2
```

See [docs/SETTINGS.md](docs/SETTINGS.md) for the full list of categories, keys and values.

### Remote control & text

```bash
lgtv button HOME                   # any remote button
lgtv button UP UP ENTER            # sequences work
lgtv button DOWN --repeat 3
lgtv buttons                       # list all button names
lgtv text "stranger things"        # type into the focused search box
lgtv enter                         # press OK in the text field
lgtv delete 5                      # backspace x5
```

### Channels, playback, notifications

```bash
lgtv channel up | lgtv channel down | lgtv channel 5
lgtv channels                      # list channels
lgtv media play|pause|stop|rewind|ff
lgtv notify "Dinner is ready!"     # toast popup on the TV
```

### Power users

```bash
lgtv info                          # model / firmware info
lgtv sw-info                       # firmware details incl. MAC address
lgtv raw ssap://audio/getVolume    # send any raw SSAP request
lgtv raw ssap://tv/switchInput '{"inputId": "HDMI_2"}'
```

## Python API

```python
from lgtvpy import LGTV

# Context manager connects (pairing on first ever use) and cleans up.
with LGTV() as tv:                      # your paired TV; or LGTV("192.168.1.61")
    tv.set_volume(15)
    tv.set_input("HDMI_2")
    tv.launch_app("netflix")
    tv.button("HOME")
    tv.notify("Hello!")

    # Settings - any category/key the TV supports:
    tv.set_picture_mode("filmMaker")
    tv.set_picture_settings({"backlight": 40, "contrast": 85})
    tv.set_settings("sound", {"soundMode": "movie"})
    print(tv.get_picture_settings())

# Power on works while the TV is off (Wake-on-LAN):
LGTV().power_on()
```

Full method reference: [docs/API.md](docs/API.md). Example scripts (movie-night scene, game-mode toggle) are in [examples/](examples/).

## Troubleshooting

| Problem | Fix |
|---|---|
| `Could not connect to TV` | TV fully off (standby blocks the API) → `lgtv on` first, or check it's on the same network: `ping <tv-ip>`. |
| No pairing prompt appears | The TV must be on (not screensaver/standby). Re-run `lgtv pair`. Check *Settings → General → Devices → Mobile Connection Management* hasn't blocked new devices. |
| `403` / pairing rejected errors after working before | The TV revoked the key (factory reset, or you denied a prompt). Delete `~/.lgtv/config.json` and pair again. |
| `lgtv on` does nothing | Enable **Turn On via Wi-Fi** on the TV (see above). Wired ethernet is the most reliable for WoL. If the MAC wasn't auto-stored, run `lgtv sw-info` while the TV is on — `device_id` is the MAC — then `lgtv on --mac aa:bb:cc:dd:ee:ff`. |
| A settings write silently does nothing | The key or value isn't valid for your firmware. Verify with `lgtv settings get <category> <key>` before/after. See [docs/SETTINGS.md](docs/SETTINGS.md). |
| Firewall prompt on first run | Allow Python on **private** networks — outbound WebSocket + UDP broadcast (WoL) is all it uses. |
| Occasional `Could not connect` / connection reset | The TV rate-limits rapid back-to-back connections. The client already retries 3×; just re-run the command if it still slips through. |
| `lgtv info` shows firmware fields instead of model name | Newer firmware (webOS 25) blocks the model-info endpoint for third-party clients; the tool falls back to software info automatically. |

## Development & tests

```bash
pip install -e ".[test]"
```

```bash
pytest
```

The unit suite (~80 tests) runs fully offline — a scripted fake TV answers the SSAP protocol — so it works in CI. There's also an opt-in **live** suite of read-only checks against your real, already-paired TV (it must be on; nothing is changed):

```bash
LGTV_LIVE=1 pytest -m live          # bash
```

```powershell
$env:LGTV_LIVE="1"; pytest -m live  # PowerShell
```

## Notes

- The pairing key in `~/.lgtv/config.json` grants control of the TV to anyone who has it — treat it like a password on shared machines.
- Settings writes use an unofficial (but long-stable) mechanism. Stick to documented keys/values; the TV does not validate garbage input.
- The protocol is local-only; nothing leaves your network.
