"""Load, apply, and capture TV setting *profiles* stored as TOML.

A profile is a small TOML file describing a desired TV state - e.g. the best
picture settings for film or gaming - so you can switch the whole TV to a look
with one command (``lgtv profile apply film.toml``).

Schema
------
Top-level scalar keys are *actions*; ``[tables]`` are *settings categories*
applied through the settings service (see docs/SETTINGS.md for keys/values)::

    name = "Film"                 # optional label
    description = "..."           # optional, ignored on apply
    input = "HDMI_1"              # optional: switch input first
    volume = 14                   # optional: absolute volume 0-100
    mute = false                  # optional
    sound_output = "external_arc" # optional
    notify = "Film mode"          # optional toast shown last

    [picture]                     # -> set_settings("picture", {...})
    pictureMode = "filmMaker"
    backlight = 60
    contrast = 85

    [sound]                       # -> set_settings("sound", {...})
    soundMode = "movie"

Application order: ``input`` -> each category table -> ``volume`` -> ``mute``
-> ``sound_output`` -> ``notify``. Within a category that names a *mode*
(``pictureMode`` / ``soundMode``) alongside other keys, the mode is applied
first in its own call - otherwise switching mode reloads that mode's stored
values and clobbers the keys you set (verified on webOS 25). Per-app picture
keys (``truMotionMode``) then go in a final write flagged ``current_app``
(see :meth:`lgtvpy.tv.LGTV.set_settings`).
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List, Union

try:  # Python 3.11+
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.9/3.10
    import tomli as tomllib

from .client import LGTVError

# Top-level scalar keys the applier understands.
_ACTION_KEYS = ("input", "volume", "mute", "sound_output")
_META_KEYS = ("name", "description", "notify")
_ALLOWED_SCALARS = frozenset(_ACTION_KEYS + _META_KEYS)

# Category -> the "mode" key that must be applied before its siblings.
_MODE_KEYS = {"picture": "pictureMode", "sound": "soundMode"}

# Seconds to wait between the mode call and the rest of a category, so the
# TV finishes applying the mode (its settings writes are asynchronous).
DEFAULT_SETTLE = 0.4

Profile = Dict[str, Any]


# -- loading / validation ---------------------------------------------------


def load(path: Union[str, Path]) -> Profile:
    """Parse and validate a TOML profile file."""
    path = Path(path)
    try:
        with path.open("rb") as handle:
            profile = tomllib.load(handle)
    except FileNotFoundError as exc:
        raise LGTVError(f"Profile not found: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise LGTVError(f"Invalid TOML in {path}: {exc}") from exc
    validate(profile)
    return profile


def validate(profile: Profile) -> None:
    """Raise LGTVError if the profile has unknown keys or bad structure."""
    if not isinstance(profile, dict):
        raise LGTVError("Profile must be a table (mapping)")
    for key, value in profile.items():
        if isinstance(value, dict):
            for sub_key, sub_value in value.items():
                if isinstance(sub_value, (dict, list)):
                    raise LGTVError(
                        f"[{key}] setting {sub_key!r} must be a scalar value"
                    )
            continue
        if key not in _ALLOWED_SCALARS:
            raise LGTVError(
                f"Unknown profile key {key!r}. Use one of "
                f"{sorted(_ALLOWED_SCALARS)}, or a [table] for a settings category "
                f"(e.g. [picture])."
            )
    if not _categories(profile) and not any(k in profile for k in _ACTION_KEYS):
        raise LGTVError("Profile does nothing: no actions and no settings categories.")


def _categories(profile: Profile) -> Dict[str, dict]:
    """The category tables (picture, sound, ...) in file order."""
    return {k: v for k, v in profile.items() if isinstance(v, dict)}


# -- planning / applying ----------------------------------------------------


def plan(profile: Profile) -> List[str]:
    """Human-readable list of what apply() would do (no TV needed)."""
    validate(profile)
    steps: List[str] = []
    if "input" in profile:
        steps.append(f"switch input -> {profile['input']}")
    for category, settings in _categories(profile).items():
        pairs = ", ".join(f"{k}={v}" for k, v in settings.items())
        steps.append(f"set {category}: {pairs}")
    if "volume" in profile:
        steps.append(f"set volume -> {profile['volume']}")
    if "mute" in profile:
        steps.append(f"set mute -> {profile['mute']}")
    if "sound_output" in profile:
        steps.append(f"set sound output -> {profile['sound_output']}")
    if "notify" in profile:
        steps.append(f"notify: {profile['notify']!r}")
    return steps


def apply(
    tv, profile: Profile, dry_run: bool = False, settle: float = DEFAULT_SETTLE
) -> List[str]:
    """Apply ``profile`` to ``tv``. Returns the list of steps taken.

    ``dry_run`` returns the plan without touching the TV. ``settle`` is the
    pause (seconds) between a mode change and the rest of that category.
    """
    steps = plan(profile)
    if dry_run:
        return steps

    if "input" in profile:
        tv.set_input(profile["input"])
    for category, settings in _categories(profile).items():
        _apply_category(tv, category, settings, settle)
    if "volume" in profile:
        tv.set_volume(profile["volume"])
    if "mute" in profile:
        tv.set_mute(profile["mute"])
    if "sound_output" in profile:
        tv.set_sound_output(profile["sound_output"])
    if "notify" in profile:
        tv.notify(profile["notify"])
    return steps


def _apply_category(tv, category: str, settings: dict, settle: float) -> None:
    settings = dict(settings)
    mode_key = _MODE_KEYS.get(category)
    if mode_key and mode_key in settings and len(settings) > 1:
        # Apply the mode alone first, let it settle, then the tuned values.
        tv.set_settings(category, {mode_key: settings.pop(mode_key)})
        if settle:
            time.sleep(settle)
    if settings:
        tv.set_settings(category, settings)


# -- capturing the current state -------------------------------------------


def capture(tv, name: str = None) -> Profile:
    """Read the TV's current input/volume/picture/sound into a profile dict.

    Picture captures every readable scalar key (PICTURE_KEYS_EXTENDED); if
    older firmware refuses that request it retries with the basic set.
    """
    from .tv import PICTURE_KEYS, PICTURE_KEYS_EXTENDED

    profile: Profile = {}
    if name:
        profile["name"] = name

    try:
        current_input = _app_to_input(tv.current_app())
        if current_input:
            profile["input"] = current_input
    except LGTVError:
        pass

    try:
        profile["volume"] = tv.volume
    except LGTVError:
        pass

    picture = {}
    for keys in (PICTURE_KEYS_EXTENDED, PICTURE_KEYS):
        try:
            current = tv.get_picture_settings(keys)
        except LGTVError:
            continue
        for key, value in current.items():
            if not isinstance(value, (dict, list)):  # profiles hold scalars only
                picture[key] = _coerce(value)
        break
    if picture:
        profile["picture"] = picture

    try:
        sound = tv.get_settings("sound", ["soundMode"])
        if sound.get("soundMode"):
            profile["sound"] = {"soundMode": sound["soundMode"]}
    except LGTVError:
        pass

    return profile


def _app_to_input(app_id: str) -> Union[str, None]:
    """'com.webos.app.hdmi2' -> 'HDMI_2'; None for non-HDMI apps."""
    if app_id and "hdmi" in app_id.lower():
        digits = app_id.lower().split("hdmi")[-1]
        if digits.isdigit():
            return f"HDMI_{digits}"
    return None


def _coerce(value: Any) -> Any:
    """Turn numeric strings the TV returns ('85') into ints for a clean file."""
    if isinstance(value, str):
        body = value[1:] if value.startswith("-") else value
        if body.isdigit():
            return int(value)
    return value


# -- serialising back to TOML ----------------------------------------------


def dumps(profile: Profile) -> str:
    """Serialise a profile dict to TOML text (scalars first, then tables)."""
    lines: List[str] = []
    for key, value in profile.items():
        if not isinstance(value, dict):
            lines.append(f"{key} = {_toml_value(value)}")
    for name, table in profile.items():
        if isinstance(table, dict):
            lines.append("")
            lines.append(f"[{name}]")
            for key, value in table.items():
                lines.append(f"{key} = {_toml_value(value)}")
    return "\n".join(lines) + "\n"


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):  # bool before int (bool is a subclass of int)
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
