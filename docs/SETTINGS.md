# Settings reference

Change any TV setting with:

```bash
lgtv settings set <category> <key> <value>
lgtv settings get <category> [keys...]
```

or in Python: `tv.set_settings(category, {key: value})` / `tv.get_settings(category, [keys])`.

Values are parsed as JSON where possible: `40` becomes a number, `true` a boolean, and quoted strings stay strings. A few keys store the *strings* `"true"`/`"false"` (noted below). Pass those quoted, e.g. `'"true"'`.

> **Where these keys come from.** LG doesn't publish this list. The keys and values below come from settings dumps of real TVs, maintained per model in [bscpylgtv's docs](https://github.com/chros73/bscpylgtv/tree/master/docs). This page follows the **2023 OLED** dump (G3, the same platform as the C3) checked against 2025 (G5, webOS 25) and 2026 (G6, webOS 26) models. Core picture and sound keys are unchanged across all three. Newer models only *add* keys, marked **2025+** below. Older TVs may lack some keys or values.

## How writes work

| | `settings set` (default) | `settings set --public` |
|---|---|---|
| Python | `tv.set_settings(...)` | `tv.set_system_settings(...)` |
| Mechanism | Luna bridge (internal settings service, via an invisible alert) | Public `ssap://settings/setSystemSettings` |
| Firmware | all webOS versions | **webOS 24 (2024) and newer** |
| Keys | every category and key on this page | a subset (see [Public API](#public-api-coverage)) |
| Errors | **none**: a bad key or value is silently ignored | the TV rejects bad writes with an error |

Either way, check with `settings get` before and after a write if a key is readable.

**Picture settings belong to the active picture mode** (per input and per SDR/HDR/Dolby Vision), just like changing them in the TV menu. Switching `pictureMode` reloads that mode's stored values. Profiles therefore apply the mode first, then the rest.

**`truMotionMode` and `aspectRatio` are stored per app.** The TV ignores them unless the write carries a `current_app` flag. `set_settings`/`set_system_settings` (and profiles) add the flag automatically, sending those keys in their own write.

## Category: `picture`

| Key | Values | Notes |
|---|---|---|
| `pictureMode` | **SDR:** `vivid`, `normal`, `eco`, `cinema`, `sports`, `game`, `filmMaker`, `expert1`, `expert2`, `photo`, `personalized` | `normal` = Standard, `expert1`/`expert2` = Expert (Bright / Dark Room). |
| | **HDR10/HLG:** `hdrVivid`, `hdrStandard`, `hdrEco`, `hdrCinema`, `hdrCinemaBright`, `hdrGame`, `hdrFilmMaker`, `hdrPersonalized` | Only while HDR content plays. |
| | **Dolby Vision:** `dolbyHdrVivid`, `dolbyHdrStandard`, `dolbyHdrCinema`, `dolbyHdrCinemaBright`, `dolbyHdrGame`, `dolbyHdrPersonalized`, `dolbyHdrDarkAmazon` | Only while DV content plays. |
| `backlight` | `0`–`100` | "OLED Pixel Brightness" (2023+) / "OLED Light": the main brightness control. |
| `contrast` | `0`–`100` | |
| `brightness` | `0`–`100` | Black level, not overall brightness. Reference is `50`. |
| `color` | `0`–`100` | Saturation. |
| `sharpness` | `0`–`50` | |
| `tint` | `-50`–`50` | |
| `colorTemperature` | `-50`–`50` | Warm ↔ cool. bscpylgtv's calibrated presets write `50` (they target Warm 50), which suggests positive = warm. Confirm on your set: pick Warm 50 in the menu, then `settings get picture colorTemperature`. |
| `energySaving` | `off`, `auto`, `min`, `med`, `max` | On 2022+ models Energy Saving overrides/locks the backlight, so set it to `off` if backlight changes don't take. On EU/UK models the first change may pop up a confirmation. |
| `gamma` | `low`, `medium`, `high1`, `high2` (+ `mediumHavingLevel` **2025+**) | `medium` ≈ 2.2, `high1` ≈ 2.4 (as used by bscpylgtv's presets). |
| `gammaLevel` | `-3`–`3` | **2025+**, used with `mediumHavingLevel`. |
| `colorGamut` | `auto`, `native`, `wide`, `extended`, `dynamic` | `auto` follows the signal (e.g. BT.709). |
| `dynamicContrast` | `off`, `low`, `medium`, `high` | |
| `dynamicColor` | `off`, `low`, `medium`, `high`, `user` | |
| `peakBrightness` | `off`, `high` | |
| `hdrDynamicToneMapping` | `on`, `off`, `HGIG` | HDR modes only. (Not `oledDynamicToneMapping`, which isn't a real key.) |
| `truMotionMode` | `off`, `cinemaClear`, `natural`, `smooth`, `clear`, `user` | Motion smoothing. Per-app: written with `current_app` automatically. |
| `truMotionJudder` / `truMotionBlur` | `0`–`10` | Used when `truMotionMode` is `user`. |
| `motionProOLED` | `off`, `low`, `medium`, `high`, `auto` | OLED Motion (black-frame insertion). |
| `realCinema` | `on`, `off` | 24p judder-free playback. |
| `noiseReduction` / `mpegNoiseReduction` | `off`, `low`, `medium`, `high`, `auto` | |
| `smoothGradation` | `off`, `low`, `medium`, `high` | |
| `superResolution` | `off`, `low`, `medium`, `high` | |
| `motionEyeCare` | `on`, `off` | |
| `eyeComfortMode` | `on`, `off` | Reduce Blue Light (Eye Comfort). |
| `nearBlackDetail` | `-3`–`3` | **2025+** |
| `logoLuminanceAdjust` | `off`, `light`, `strong` | Static-logo dimming (panel care). |
| `screenShift` | `on`, `off` | Screen Move / pixel shift (panel care). |
| `filmMakerMode` | `on`, `off` | FILMMAKER MODE auto-start. |
| `aspectRatio` | `16x9`, `original`, `4x3`, `21x9`, `just_scan`, `zoom`, `zoom2`, `cinema_zoom`, `caption_zoom` | Per-app: written with `current_app` automatically. |
| `applyToAllInput` | `picture` | Write-only trigger: copies the current mode's settings to all inputs. |

Expert calibration keys also exist: `whiteBalanceColorTemperature` (`cool`, `medium`, `warm1`, `warm2`), `whiteBalanceMethod` (`2`, `10`, `22`, `10code`, `22code`), `whiteBalanceRedGain`/`…Offset` (`-50`–`50`), 2-/10-/22-point white-balance arrays, and `colorManagement{Hue,Saturation,Luminance}{Red,Green,Blue,Cyan,Magenta,Yellow}` (`-30`–`30`). `blackLevel` (a per-signal-type table) and `adjustingLuminance` (an array) are not single values, so profiles can't hold them.

```bash
# Dark-room movie setup
lgtv settings set picture pictureMode filmMaker
lgtv settings set picture backlight 35
lgtv settings set picture energySaving off
lgtv settings set picture truMotionMode off        # current_app flag added for you
```

## Category: `aiPicture`

| Key | Values | Notes |
|---|---|---|
| `ai_Picture` | `on`, `off` | AI Picture Pro |
| `ai_Brightness` | `on`, `off` | AI Brightness |
| `ai_Genre` | `on`, `off` | AI Genre Selection |

## Category: `sound`

| Key | Values | Notes |
|---|---|---|
| `soundMode` | `aiSoundPlus`, `standard`, `movie`, `news`, `sports`, `music`, `game`, `bassBlast` | Luna bridge only (not accepted by `--public`). |
| `clearVoice` | `off`, `level1`, `level2`, `level3` | Dialogue enhancement (a separate key, not a sound mode). |
| `soundOutput` | prefer `lgtv sound-output <value>`: `tv_speaker`, `external_arc`, `external_optical`, `bt_soundbar`, `headphone`, `lineout`, `wisa_speaker`, `tv_external_speaker`, `tv_speaker_headphone`, … | |
| `soundOutputDigital` | `auto`, `pcm`, `passThrough` | Digital (eARC/optical) output format. |
| `eArcSupport` | `on`, `off` | |
| `avSyncBypassInput` | `on`, `off` | AV-sync bypass. |
| `avSyncSpeaker` / `avSyncSpdif` | `0`–`60` | AV-sync delay. |
| `inputAudioFormatHDMI1`…`4` | `bitstream`, `pcm` | |
| `digitalAudioPriority` | `auto`, `mpeg`, `dolbyDigital`, `dobyDigitalPlus`, `heAaC`, `dra` | Spelling (`doby…`) is LG's. |
| `magicSpaceSound` | `off`, `standard`, `bass`, `treble` | |
| `tvSetupConfiguration` | `stand`, `wall_mount` | Sound optimiser for TV placement. |
| `audioBalance` | `-50`–`50` | |

## Category: `other` (gaming, HDMI, panel care)

| Key | Values | Notes |
|---|---|---|
| `enableALLM` | `on`, `off` | Auto Low Latency Mode. |
| `gameOptimization`, `gameOptimizationHDMI1`…`4` | `on`, `off` | Game Optimizer, globally / per input. |
| `gameGenre` | `Standard`, `FPS`, `RPG`, `RTS`, `Sports`, `USER` | Game Optimizer genre preset. |
| `blackStabilizer` / `whiteStabilizer` | `0`–`20` | Game Optimizer. |
| `blueLight` | `off`, `level1`, `level2` | Blue-light reduction level. |
| `darkMode` | `off`, `level1`, `level2` | Dark mode level. |
| `freesyncOLEDHDMI1`…`4` | `on`, `off` | AMD FreeSync Premium per input. |
| `qmsVrr` | `on`, `off` | QMS-VRR. |
| `hdmiPcMode` | `{"hdmi1": false, "hdmi2": true, "hdmi3": false, "hdmi4": false}` | PC mode per input. A JSON table, so CLI or Python only, not profiles. Safest to send all four inputs. |
| `uhdDeepColorHDMI1`…`4` | `on`, `off` | HDMI Ultra HD Deep Colour (needed for high-bandwidth 4K HDR / 120 Hz signals). |
| `eotf`, `eotfHDMI1`…`4` | `auto`, `sdrGamma`, `hdrGamma`, `st2084`, `hlg` | HDMI Signal Override. |
| `colorimetry`, `colorimetryHDMI1`…`4` | `auto`, `bt709`, `bt601`, `bt2020`, `p3D65` | HDMI Signal Override. |
| `masteringPeak` / `maxCLL` / `maxFALL` (+`HDMI1`…`4`) | `auto`, `0`, `400`, `540`, `700`, `1000`, `2000`, `3000`, `4000`, `10000` | HDMI Signal Override HDR metadata. |
| `simplinkEnable` | `on`, `off` | HDMI-CEC (SIMPLINK). |
| `oledCareMode` | `off`, `comfortCare`, `cinemaCare`, `kidsCare` | |
| `lgLogoDisplay` | `on`, `off` | LG logo at power-on. |

**2026+** adds Game Dashboard extras such as `fpsCounter` (`off`, `topLeft`, `topRight`, `bottomLeft`, `bottomRight`) and `crosshair` (`off`, `redCross`, `greenCross`, `redDot`, `greenDot`).

```bash
lgtv settings set other enableALLM on
lgtv settings set other hdmiPcMode '{"hdmi1": false, "hdmi2": true, "hdmi3": false, "hdmi4": false}'
```

## Category: `aspectRatio`

| Key | Values |
|---|---|
| `arcPerApp` | e.g. `original`, `16x9` |
| `justScan` | `auto`, `on`, `off` |

## Other categories

| Category | Useful keys |
|---|---|
| `network` | `wolwowlOnOff`: string `"true"`/`"false"`, "Turn On via Wi-Fi/LAN" (needed for `lgtv on`). `deviceName`. |
| `option` | `quickStartMode` (`on`/`off`, Quick Start+), `audioGuidance`, `country`, `livePlus`. |
| `support` | `automaticUpdate` (`on`/`off`): automatic firmware updates (see the README's webOS 26 note). |
| `time` | `automaticStandBy` (`0`, `2`, `4`, `6`, `8` hours), `autoOff2HourOnTimer` (`on`/`off`). |
| `general` | `homeAutoLaunch`, `homePromotion`, `noSignalScreenSaver`, `screenSaverAd` (`on`/`off`). |

```bash
lgtv settings set network wolwowlOnOff '"true"'    # the TV stores a string here
```

## Public API coverage

`settings get` reads through the public API, which only returns **allow-listed** keys. Asking for anything else gets an error or is left out of the reply. `settings set --public` writes through the same API with a similar allow-list. On 2023–2026 OLEDs:

| Category | Readable (`get`) and writable (`set --public`) |
|---|---|
| `picture` | `pictureMode`, `backlight`, `contrast`, `brightness`, `color`, `sharpness`, `tint`, `colorTemperature`, `energySaving`, `gamma`, `colorGamut`, `dynamicContrast`, `dynamicColor`, `peakBrightness`, `hdrDynamicToneMapping`, `truMotionMode`, `realCinema`, `motionEyeCare`, `noiseReduction`, `mpegNoiseReduction`, `smoothGradation`, `superResolution`, `blackLevel`, `adjustingLuminance`, white-balance and colour-management keys, `eyeComfortMode` (2025+) |
| `sound` | `soundOutput`, `soundOutputDigital`, `eArcSupport`, `avSync`, `avSyncSpdif`, `avSyncBypassInput`, `tvSetupConfiguration`. `soundMode` is **read-only** here. |
| `other` | `simplinkEnable`, `uhdDeepColorHDMI1`…`4`, `gameWallpaper` |
| `aspectRatio` | `arcPerApp`, `justScan` |
| `general` | `homeAutoLaunch`, `homePromotion`, `alwaysOn`, `tvOnScreen`, `lifeOnScreenMode` (and a few more) |
| `network` | `deviceName`, `wolwowlOnOff` |
| `option` | `quickStartMode`, `audioGuidance`, `country`, `livePlus` (and a few regional keys) |
| `support` / `time` | `automaticUpdate` / `timeZone` |

Everything else (Game Optimizer, `aiPicture`, `soundMode`, HDMI Signal Override, …) can be **written** with the default Luna bridge but not read back.

## Discovering what your TV supports

Read before you write. Ask for the key you're interested in and see whether the TV returns it:

```bash
lgtv settings get picture backlight contrast pictureMode truMotionMode
lgtv settings get sound soundMode
```

If a key comes back, that exact spelling is what `settings set` needs. For deep exploration, the raw command hits the settings API directly:

```bash
lgtv raw ssap://settings/getSystemSettings '{"category": "picture", "keys": ["backlight"]}'
```

The per-model dumps linked at the top list every key, including ones not covered here (`caption`, `lock`, `channel`, `twinTv`, …).
