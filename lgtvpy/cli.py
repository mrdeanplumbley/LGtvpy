"""Command-line interface: ``lgtv <command>`` (or ``python -m lgtvpy <command>``).

Run ``lgtv --help`` or see README.md for the full command reference.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Optional

from . import config as _config
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

    sub.add_parser("pair", help="pair with the TV (first time: lgtv pair --ip <tv-ip>)")
    sub.add_parser("status", help="power / app / volume summary")
    sub.add_parser("info", help="system info (model, firmware)")
    sub.add_parser("sw-info", help="software info (includes MAC address)")

    p = sub.add_parser("on", help="power on via Wake-on-LAN")
    p.add_argument("--mac", help="TV MAC address (auto-stored after first pairing)")
    sub.add_parser("off", help="power off (standby)")
    sub.add_parser("screen-off", help="panel off, apps/audio keep running")
    sub.add_parser("screen-on", help="panel back on")

    p = sub.add_parser("vol", help="show or set volume: vol | vol 15 | vol up|down")
    p.add_argument("level", nargs="?", help="0-100, 'up' or 'down'")
    p = sub.add_parser("mute", help="mute on|off, or toggle with no argument")
    p.add_argument("state", nargs="?", choices=["on", "off"])
    p = sub.add_parser("sound-output", help="show or set sound output")
    p.add_argument(
        "output", nargs="?", help="e.g. tv_speaker, external_arc, bt_soundbar"
    )

    sub.add_parser("apps", help="list installed apps")
    sub.add_parser("app", help="show foreground app id")
    p = sub.add_parser("launch", help="launch an app by id")
    p.add_argument("app_id", help="e.g. netflix, youtube.leanback.v4")
    p.add_argument("--params", help="JSON params for the app")
    p = sub.add_parser("close", help="close an app by id")
    p.add_argument("app_id")
    p = sub.add_parser("open", help="open a URL in the TV browser")
    p.add_argument("url")

    sub.add_parser("inputs", help="list HDMI/external inputs")
    p = sub.add_parser("input", help="switch input")
    p.add_argument("input_id", help="e.g. HDMI_1, HDMI_2")

    p = sub.add_parser("channel", help="channel up|down|<number>")
    p.add_argument("target", help="'up', 'down' or a channel number/id")
    sub.add_parser("channels", help="list TV channels")

    p = sub.add_parser("media", help="playback control")
    p.add_argument("action", choices=["play", "pause", "stop", "rewind", "ff"])

    p = sub.add_parser("button", help="press remote button(s), e.g. button HOME")
    p.add_argument("names", nargs="+", metavar="NAME")
    p.add_argument("--repeat", type=int, default=1)
    sub.add_parser("buttons", help="list known button names")

    p = sub.add_parser("text", help="type text into the focused field on the TV")
    p.add_argument("text")
    sub.add_parser("enter", help="press Enter in the focused text field")
    p = sub.add_parser("delete", help="delete characters in the focused field")
    p.add_argument("count", nargs="?", type=int, default=1)

    p = sub.add_parser("notify", help="show a toast message on the TV")
    p.add_argument("message")

    p = sub.add_parser("settings", help="read/write system settings")
    settings_sub = p.add_subparsers(dest="settings_command", required=True)
    g = settings_sub.add_parser("get", help="settings get picture [keys...]")
    g.add_argument("category")
    g.add_argument("keys", nargs="*")
    s = settings_sub.add_parser("set", help="settings set picture backlight 40")
    s.add_argument("category")
    s.add_argument("key")
    s.add_argument("value")

    p = sub.add_parser("picture-mode", help="e.g. cinema, filmMaker, game, expert1")
    p.add_argument("mode")
    p = sub.add_parser("sound-mode", help="e.g. aiSoundPlus, standard, movie")
    p.add_argument("mode")
    p = sub.add_parser("backlight", help="OLED light / backlight 0-100")
    p.add_argument("level", type=int)
    p = sub.add_parser("energy-saving", help="off, min, med, max, auto")
    p.add_argument("level")

    p = sub.add_parser("raw", help="send a raw ssap:// request")
    p.add_argument("uri", help="e.g. ssap://audio/getVolume")
    p.add_argument("payload", nargs="?", help="JSON payload")

    return parser


def run(args: argparse.Namespace) -> Any:  # noqa: C901 - simple dispatch table
    cmd = args.command

    # Wake-on-LAN must work without a connection (the TV is off).
    if cmd == "on":
        tv = LGTV(args.ip, timeout=args.timeout)
        tv.power_on(mac=args.mac)
        return f"Magic packet sent to {args.ip}. The TV should wake shortly."

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
