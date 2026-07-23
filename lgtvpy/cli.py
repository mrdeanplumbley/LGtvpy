"""Command-line interface: ``lgtv <command>`` (or ``python -m lgtvpy <command>``).

Run ``lgtv --help`` or see README.md for the full command reference.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from . import config as _config
from . import profiles
from .client import LGTVError
from .keys import BUTTONS
from .tv import LGTV


def _parse_value(raw: str) -> Any:
    """Parse CLI setting values: numbers/bools/JSON pass through, else string."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _print(data: Any) -> None:
    if isinstance(data, (dict, list)):
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif data is not None:
        print(data)


def _pair_prompt() -> None:
    print(">> Check the TV: accept the connection prompt with your remote...")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lgtv",
        description="Control an LG webOS TV over the local network.",
    )
    parser.add_argument(
        "--ip",
        default=None,
        help="TV IP address (default: the TV you've paired)",
    )
    parser.add_argument(
        "--timeout", type=float, default=10.0, help="request timeout in seconds"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Accept --ip/--timeout after the subcommand too (lgtv pair --ip 10.0.0.5).
    # SUPPRESS keeps the subparser from clobbering a value parsed by the root.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--ip", default=argparse.SUPPRESS, help=argparse.SUPPRESS)
    common.add_argument(
        "--timeout", type=float, default=argparse.SUPPRESS, help=argparse.SUPPRESS
    )

    def add(name: str, **kwargs):
        return sub.add_parser(name, parents=[common], **kwargs)

    add("pair", help="pair with the TV (first time: lgtv pair --ip <tv-ip>)")
    add("status", help="power / app / volume summary")
    add("info", help="system info (model, firmware)")
    add("sw-info", help="software info (includes MAC address)")

    p = add("on", help="power on via Wake-on-LAN")
    p.add_argument("--mac", help="TV MAC address (auto-stored after first pairing)")
    add("off", help="power off (standby)")
    add("screen-off", help="panel off, apps/audio keep running")
    add("screen-on", help="panel back on")

    p = add("vol", help="show or set volume: vol | vol 15 | vol up|down")
    p.add_argument("level", nargs="?", help="0-100, 'up' or 'down'")
    p = add("mute", help="mute on|off, or toggle with no argument")
    p.add_argument("state", nargs="?", choices=["on", "off"])
    p = add("sound-output", help="show or set sound output")
    p.add_argument(
        "output", nargs="?", help="e.g. tv_speaker, external_arc, bt_soundbar"
    )

    add("apps", help="list installed apps")
    add("app", help="show foreground app id")
    p = add("launch", help="launch an app by id")
    p.add_argument("app_id", help="e.g. netflix, youtube.leanback.v4")
    p.add_argument("--params", help="JSON params for the app")
    p = add("close", help="close an app by id")
    p.add_argument("app_id")
    p = add("open", help="open a URL in the TV browser")
    p.add_argument("url")

    add("inputs", help="list HDMI/external inputs")
    p = add("input", help="switch input")
    p.add_argument("input_id", help="e.g. HDMI_1, HDMI_2")

    p = add("channel", help="channel up|down|<number>")
    p.add_argument("target", help="'up', 'down' or a channel number/id")
    add("channels", help="list TV channels")

    p = add("media", help="playback control")
    p.add_argument("action", choices=["play", "pause", "stop", "rewind", "ff"])

    p = add("button", help="press remote button(s), e.g. button HOME")
    p.add_argument("names", nargs="+", metavar="NAME")
    p.add_argument("--repeat", type=int, default=1)
    add("buttons", help="list known button names")

    p = add("text", help="type text into the focused field on the TV")
    p.add_argument("text")
    add("enter", help="press Enter in the focused text field")
    p = add("delete", help="delete characters in the focused field")
    p.add_argument("count", nargs="?", type=int, default=1)

    p = add("notify", help="show a toast message on the TV")
    p.add_argument("message")

    p = add("settings", help="read/write system settings")
    settings_sub = p.add_subparsers(dest="settings_command", required=True)
    g = settings_sub.add_parser(
        "get", parents=[common], help="settings get picture [keys...]"
    )
    g.add_argument("category")
    g.add_argument("keys", nargs="*")
    s = settings_sub.add_parser(
        "set", parents=[common], help="settings set picture backlight 40"
    )
    s.add_argument("category")
    s.add_argument("key")
    s.add_argument("value")

    p = add("profile", help="apply/show/save a TOML settings profile")
    profile_sub = p.add_subparsers(dest="profile_command", required=True)
    pa = profile_sub.add_parser(
        "apply", parents=[common], help="apply a profile: profile apply film.toml"
    )
    pa.add_argument("file", help="path to a .toml profile")
    pa.add_argument(
        "--dry-run",
        action="store_true",
        help="print what would change without touching the TV",
    )
    psh = profile_sub.add_parser(
        "show", help="print a profile's planned actions (no connection)"
    )
    psh.add_argument("file", help="path to a .toml profile")
    psv = profile_sub.add_parser(
        "save", parents=[common], help="capture current TV settings to a .toml file"
    )
    psv.add_argument("file", help="path to write")
    psv.add_argument("--name", help="name to record in the profile")

    p = add("picture-mode", help="e.g. cinema, filmMaker, game, expert1")
    p.add_argument("mode")
    p = add("sound-mode", help="e.g. aiSoundPlus, standard, movie")
    p.add_argument("mode")
    p = add("backlight", help="OLED light / backlight 0-100")
    p.add_argument("level", type=int)
    p = add("energy-saving", help="off, min, med, max, auto")
    p.add_argument("level")

    p = add("raw", help="send a raw ssap:// request")
    p.add_argument("uri", help="e.g. ssap://audio/getVolume")
    p.add_argument("payload", nargs="?", help="JSON payload")

    return parser


def run(args: argparse.Namespace) -> Any:  # noqa: C901 - simple dispatch table
    cmd = args.command

    # Wake-on-LAN must work without a connection (the TV is off).
    if cmd == "on":
        tv = LGTV(args.ip, timeout=args.timeout)
        tv.power_on(mac=args.mac)
        return f"Magic packet sent to {tv.ip}. The TV should wake shortly."

    # 'profile show' just parses the file - no TV needed.
    if cmd == "profile" and args.profile_command == "show":
        profile = profiles.load(args.file)
        return {
            "profile": profile.get("name", args.file),
            "actions": profiles.plan(profile),
        }

    with LGTV(args.ip, timeout=args.timeout, on_pair_prompt=_pair_prompt) as tv:
        if cmd == "pair":
            entry = _config.get_tv(tv.ip)
            return (
                f"Paired with {tv.ip}.\n"
                f"Client key stored in {_config.DEFAULT_PATH}\n"
                f"MAC address: {entry.get('mac', 'unknown')}"
            )
        if cmd == "status":
            return tv.status()
        if cmd == "info":
            return tv.system_info()
        if cmd == "sw-info":
            return tv.software_info()
        if cmd == "off":
            tv.power_off()
            return "TV switched to standby."
        if cmd == "screen-off":
            tv.screen_off()
            return "Screen off (apps keep running)."
        if cmd == "screen-on":
            tv.screen_on()
            return "Screen on."

        if cmd == "vol":
            if args.level is None:
                return {"volume": tv.volume, "muted": tv.muted}
            if args.level == "up":
                tv.volume_up()
            elif args.level == "down":
                tv.volume_down()
            else:
                tv.set_volume(int(args.level))
            return {"volume": tv.volume}
        if cmd == "mute":
            if args.state is None:
                return {"muted": tv.toggle_mute()}
            tv.set_mute(args.state == "on")
            return {"muted": args.state == "on"}
        if cmd == "sound-output":
            if args.output:
                tv.set_sound_output(args.output)
            return {"sound_output": tv.get_sound_output()}

        if cmd == "apps":
            return [
                {"id": app.get("id"), "title": app.get("title")}
                for app in tv.list_apps()
                if app.get("id")
            ]
        if cmd == "app":
            return {"app": tv.current_app()}
        if cmd == "launch":
            params = json.loads(args.params) if args.params else None
            return tv.launch_app(args.app_id, params)
        if cmd == "close":
            tv.close_app(args.app_id)
            return f"Closed {args.app_id}."
        if cmd == "open":
            return tv.open_url(args.url)

        if cmd == "inputs":
            return [
                {
                    "id": d.get("id"),
                    "label": d.get("label"),
                    "connected": d.get("connected"),
                }
                for d in tv.list_inputs()
            ]
        if cmd == "input":
            tv.set_input(args.input_id)
            return f"Switched to {args.input_id}."

        if cmd == "channel":
            if args.target == "up":
                tv.channel_up()
            elif args.target == "down":
                tv.channel_down()
            else:
                tv.set_channel(args.target)
            return "OK"
        if cmd == "channels":
            return [
                {"number": c.get("channelNumber"), "name": c.get("channelName")}
                for c in tv.list_channels()
            ]

        if cmd == "media":
            {
                "play": tv.play,
                "pause": tv.pause,
                "stop": tv.stop,
                "rewind": tv.rewind,
                "ff": tv.fast_forward,
            }[args.action]()
            return "OK"

        if cmd == "button":
            for name in args.names:
                tv.button(name, repeat=args.repeat)
            return "OK"
        if cmd == "buttons":
            return BUTTONS

        if cmd == "text":
            tv.type_text(args.text)
            return "OK"
        if cmd == "enter":
            tv.send_enter()
            return "OK"
        if cmd == "delete":
            tv.delete_chars(args.count)
            return "OK"

        if cmd == "notify":
            tv.notify(args.message)
            return "Notification sent."

        if cmd == "settings":
            if args.settings_command == "get":
                return tv.get_settings(args.category, args.keys or None)
            tv.set_settings(args.category, {args.key: _parse_value(args.value)})
            return f"Set {args.category}.{args.key} = {args.value}"

        if cmd == "profile":
            if args.profile_command == "apply":
                profile = profiles.load(args.file)
                steps = profiles.apply(tv, profile, dry_run=args.dry_run)
                label = profile.get("name", args.file)
                verb = "Would apply" if args.dry_run else "Applied"
                return {verb: label, "steps": steps}
            # save
            profile = tv.capture_profile(name=args.name)
            Path(args.file).write_text(profiles.dumps(profile), encoding="utf-8")
            return f"Saved current settings to {args.file}"

        if cmd == "picture-mode":
            tv.set_picture_mode(args.mode)
            return f"Picture mode -> {args.mode}"
        if cmd == "sound-mode":
            tv.set_sound_mode(args.mode)
            return f"Sound mode -> {args.mode}"
        if cmd == "backlight":
            tv.set_backlight(args.level)
            return f"Backlight -> {args.level}"
        if cmd == "energy-saving":
            tv.set_energy_saving(args.level)
            return f"Energy saving -> {args.level}"

        if cmd == "raw":
            payload = json.loads(args.payload) if args.payload else None
            return tv.request(args.uri, payload)

    raise LGTVError(f"Unhandled command: {cmd}")


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _print(run(args))
        return 0
    except LGTVError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
