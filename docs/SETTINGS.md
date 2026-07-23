# Settings reference

Change any TV setting with:

```bash
lgtv settings set <category> <key> <value>
lgtv settings get <category> [keys...]
```

or in Python: `tv.set_settings(category, {key: value})` / `tv.get_settings(category, [keys])`.

Values are parsed as JSON where possible — `40` becomes a number, `true` a boolean, quoted strings stay strings.

> **Important:** these keys go straight into the TV's settings service, which does **not** validate them. A wrong value is usually just ignored, but stick to the documented ones. Exact key availability varies by model year and firmware — use `settings get` to check what your TV reports before and after writing.

## Category: `picture`

| Key | Values | Notes |
|---|---|---|
| `pictureMode` | `vivid`, `normal`, `eco`, `cinema`, `sports`, `game`, `filmMaker`, `expert1`, `expert2` | `expert1` = Expert (Bright Room), `expert2` = Expert (Dark Room). While HDR/Dolby Vision content plays, the active mode set uses HDR names instead (`hdrCinema`, `hdrGame`, `hdrFilmMaker`, `dolbyHdrCinema`, ...). |
| `backlight` | `0`–`100` | "OLED Light" on OLED models — the main brightness control. |
| `brightness` | `0`–`100` | Black level, not overall brightness. Default 50. |
| `contrast` | `0`–`100` | |
| `color` | `0`–`100` | Saturation. |
| `sharpness` | `0`–`50` | |
| `tint` | `-50`–`50` | |
| `colorTemperature` | `-50`–`50` | Warm ↔ cool. |
| `energySaving` | `off`, `min`, `med`, `max`, `auto`, `screen_off` | On 2022+ models Energy Saving overrides/locks the backlight — set it to `off` if backlight changes don't take. |
| `oledDynamicToneMapping` (a.k.a. Dynamic Tone Mapping) | `on`, `off`, `HGIG` | HDR only. |
| `truMotionMode` | `off`, `smooth`, `clear`, `user` | Motion smoothing. |
| `realCinema` | `on`, `off` | |
| `noiseReduction` / `mpegNoiseReduction` | `off`, `low`, `medium`, `high`, `auto` | |
| `dynamicContrast` | `off`, `low`, `medium`, `high` | |
| `peakBrightness` | `off`, `low`, `medium`, `high` | |
| `gamma` | e.g. `low`, `medium`, `high1`, `high2` | Expert modes. |
| `colorGamut` | `auto`, `extended`, `wide`, `srgb`, `native` | Expert modes. |

Picture settings apply to the **currently active picture mode** (per input), just like changing them in the TV menu.

```bash
# Dark-room movie setup
lgtv settings set picture pictureMode filmMaker
lgtv settings set picture backlight 35
lgtv settings set picture energySaving off
```

## Category: `sound`

| Key | Values |
|---|---|
| `soundMode` | `aiSoundPlus`, `standard`, `movie`, `clearVoice`, `sports`, `music`, `game` |
| `soundOutput` | prefer `lgtv sound-output <value>` (uses the proper API): `tv_speaker`, `external_arc`, `external_optical`, `bt_soundbar`, `headphone`, `lineout` |

## Category: `aiPicture` (2022+ models)

| Key | Values |
|---|---|
| `ai_Picture` | `on`, `off` |
| `ai_Brightness` | `on`, `off` |
| `ai_Genre` | `on`, `off` |

## Category: `option`

General/system options — e.g. `subtitleEnable` (`on`/`off`), `menuLanguage` (e.g. `eng`), `country`. Explore with `lgtv settings get option <key>`.

## Category: `network` / `twinTv` / `time` ...

Exist but rarely useful to write. `settings get time currentTime` style reads work.

## Discovering what your TV supports

Read before you write — ask for the key you're interested in and see whether the TV returns it:

```bash
lgtv settings get picture backlight contrast pictureMode truMotionMode
lgtv settings get sound soundMode
```

If a key comes back in the response, that exact spelling is what `settings set` needs. If it's missing, your firmware calls it something else (key names occasionally change between webOS versions).

For deep exploration, the raw command lets you hit the settings API directly:

```bash
lgtv raw ssap://settings/getSystemSettings '{"category": "picture", "keys": ["backlight"]}'
```
