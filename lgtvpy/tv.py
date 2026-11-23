"""High-level control API for an LG webOS TV.

Wraps :class:`lgtvpy.client.WebOSClient` with friendly methods for power,
volume, inputs, apps, channels, playback, remote buttons, text entry,
notifications and - via the Luna settings-service bridge - every picture /
sound / system setting the TV exposes.

Example::

    from lgtvpy import LGTV

    with LGTV() as tv:  # defaults to your paired TV; or LGTV("192.168.1.61")
        tv.set_volume(12)
        tv.set_input("HDMI_2")
        tv.set_picture_settings({"backlight": 40, "contrast": 85})
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Optional, Tuple

from . import config as _config
from .client import (
    LGTVError,
    PAIR_TIMEOUT,
    PointerInputSocket,
    RequestError,
    WebOSClient,
)
from .wol import send_magic_packet

# Default keys fetched by get_picture_settings() - all standard on C-series.
PICTURE_KEYS = [
    "backlight",
    "brightness",
    "contrast",
    "color",
    "sharpness",
    "pictureMode",
    "energySaving",
]

# Every *scalar* picture key the public settings API lets clients read on
# webOS 23-26 OLEDs (per bscpylgtv's per-model settings docs). Used by
# capture_profile(); older firmware may refuse some, so it falls back to
# PICTURE_KEYS. (blackLevel / adjustingLuminance are readable too, but are
# per-signal dicts / arrays, which profiles can't hold.)
PICTURE_KEYS_EXTENDED = PICTURE_KEYS + [
    "tint",
    "colorTemperature",
    "gamma",
    "colorGamut",
    "dynamicContrast",
    "dynamicColor",
    "peakBrightness",
    "hdrDynamicToneMapping",
    "truMotionMode",
    "motionEyeCare",
    "realCinema",
    "noiseReduction",
    "mpegNoiseReduction",
    "smoothGradation",
    "superResolution",
]

# Picture keys the settings service only applies when the write is flagged
# with "current_app": true (they're stored per app). Without the flag the
# write is silently ignored. set_settings() sends these in their own call.
CURRENT_APP_KEYS = frozenset({"truMotionMode", "aspectRatio"})

_REDUCED_PERMISSIONS_HINT = (
    " - this TV only granted a reduced-permission pairing (webOS 26+ firmware "
    "rejects the signed manifest), so it refuses some calls"
)


def _split_current_app(
    category: str, settings: dict, current_app: Optional[bool]
) -> List[Tuple[dict, Optional[bool]]]:
    """Split a settings write into ``(settings, current_app flag)`` chunks.

    An explicit ``current_app`` applies to the whole write. Otherwise any
    picture :data:`CURRENT_APP_KEYS` go last, in their own flagged write.
    """
    if current_app is not None or category != "picture":
        return [(settings, current_app)]
    plain = {k: v for k, v in settings.items() if k not in CURRENT_APP_KEYS}
    flagged = {k: v for k, v in settings.items() if k in CURRENT_APP_KEYS}
    chunks: List[Tuple[dict, Optional[bool]]] = []
    if plain or not flagged:
        chunks.append((plain, None))
    if flagged:
        chunks.append((flagged, True))
    return chunks


class LGTV:
    """One TV, addressed by IP. Connects (and pairs) lazily on first use."""

    def __init__(
        self,
        ip: Optional[str] = None,
        client_key: Optional[str] = None,
        config_path: Optional[Path] = None,
        timeout: float = 10.0,
        on_pair_prompt: Optional[Callable[[], None]] = None,
    ):
        resolved = ip or _config.get_default_ip(config_path)
        if not resolved:
            raise LGTVError(
                "No TV IP given and no single paired TV to default to. "
                "Pass ip='...' (CLI: --ip), or pair first: lgtv pair --ip <tv-ip>"
            )
        self.ip = resolved
        self._config_path = config_path
        self._explicit_key = client_key
        self.timeout = timeout
        self.on_pair_prompt = on_pair_prompt
        self._client: Optional[WebOSClient] = None
        self._pointer: Optional[PointerInputSocket] = None

    # ------------------------------------------------------------------ #
    # Connection / pairing
    # ------------------------------------------------------------------ #

    def connect(self, pair_timeout: float = PAIR_TIMEOUT) -> "LGTV":
        """Connect and authenticate. First ever call triggers the TV's
        pairing prompt - accept it with the remote within ``pair_timeout``
        seconds. The pairing key is stored in ``~/.lgtv/config.json`` so
        subsequent connections are silent."""
        stored = _config.get_tv(self.ip, self._config_path)
        key = self._explicit_key or stored.get("client_key")

        client = WebOSClient(self.ip, timeout=self.timeout)
        client.connect()
        try:
            new_key = client.register(
                key, timeout=pair_timeout, on_prompt=self.on_pair_prompt
            )
        except Exception:
            client.close()
            raise
        self._client = client

        if new_key != key:
            _config.update_tv(self.ip, self._config_path, client_key=new_key)
        self._remember_mac()
        return self

    def close(self) -> None:
        if self._pointer is not None:
            self._pointer.close()
            self._pointer = None
        if self._client is not None:
            self._client.close()
            self._client = None

    def __enter__(self) -> "LGTV":
        return self.connect()

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def client(self) -> WebOSClient:
        """The underlying low-level client (auto-connects)."""
        if self._client is None or not self._client.connected:
            self.connect()
        assert self._client is not None
        return self._client

    def request(self, uri: str, payload: Optional[dict] = None) -> dict:
        """Send a raw ssap:// request - escape hatch for anything not wrapped."""
        client = self.client
        try:
            return client.request(uri, payload)
        except RequestError as exc:
            if not client.signed_manifest and "401" in str(exc):
                raise RequestError(f"{exc}{_REDUCED_PERMISSIONS_HINT}") from exc
            raise

    @property
    def signed_pairing(self) -> bool:
        """False if the TV only accepted the reduced-permission (unsigned)
        pairing - see README, "webOS 26"."""
        return self.client.signed_manifest

    def _remember_mac(self) -> None:
        """Store the TV's MAC (needed for Wake-on-LAN power-on) if unknown.

        Prefers ``device_id`` from software info (the active interface).
        That call needs the signed pairing, so on webOS 26 this falls back
        to the connection manager, which lists the wired and Wi-Fi MACs
        without saying which is in use - both are stored and woken.
        """
        if _config.get_tv(self.ip, self._config_path).get("mac"):
            return
        mac = None
        try:
            mac = self.software_info().get("device_id")
        except LGTVError:
            pass
        if not mac:
            try:
                info = self.connection_info()
                found = [
                    (info.get(section) or {}).get("macAddress")
                    for section in ("wiredInfo", "wifiInfo")
                ]
                found = [m for m in found if m and m.strip("0:-")]
                mac = found[0] if len(found) == 1 else found or None
            except LGTVError:
                pass  # non-fatal; power_on() will explain if the MAC is missing
        if mac:
            _config.update_tv(self.ip, self._config_path, mac=mac)

    # ------------------------------------------------------------------ #
    # Power
    # ------------------------------------------------------------------ #

    def power_off(self) -> None:
        """Put the TV into standby."""
        self.request("ssap://system/turnOff")

    def power_on(self, mac: Optional[str] = None) -> None:
        """Wake the TV via Wake-on-LAN (works without a live connection).

        Uses the MAC(s) stored during pairing unless one is passed. Requires
        the TV's "Turn On via Wi-Fi" / Quick Start+ setting to be enabled.
        """
        stored = mac or _config.get_tv(self.ip, self._config_path).get("mac")
        macs = [stored] if isinstance(stored, str) else list(stored or [])
        if not macs:
            raise LGTVError(
                "No MAC address known for this TV. Connect once while it is on "
                "(so it can be auto-detected) or pass mac='aa:bb:cc:dd:ee:ff'."
            )
        for address in macs:
            send_magic_packet(address)

    def screen_off(self) -> None:
        """Turn just the panel off - audio and apps keep running."""
        self.request(
            "ssap://com.webos.service.tvpower/power/turnOffScreen",
            {"standbyMode": "active"},
        )

    def screen_on(self) -> None:
        """Turn the panel back on after screen_off()."""
        self.request(
            "ssap://com.webos.service.tvpower/power/turnOnScreen",
            {"standbyMode": "active"},
        )

    def power_state(self) -> dict:
        """e.g. {'state': 'Active', ...} or {'state': 'Screen Off', ...}"""
        return self.request("ssap://com.webos.service.tvpower/power/getPowerState")

    # ------------------------------------------------------------------ #
    # Volume / audio
    # ------------------------------------------------------------------ #

    def get_volume(self) -> dict:
        """Raw volume status. Use ``volume`` / ``muted`` for parsed values."""
        return self.request("ssap://audio/getVolume")

    @property
    def volume(self) -> int:
        payload = self.get_volume()
        status = payload.get("volumeStatus", payload)  # webOS 22+ nests it
        return int(status.get("volume", -1))

    @property
    def muted(self) -> bool:
        payload = self.get_volume()
        status = payload.get("volumeStatus", payload)
        return bool(status.get("muteStatus", status.get("muted", False)))

    def set_volume(self, level: int) -> None:
        """Set absolute volume (0-100)."""
        if not 0 <= level <= 100:
            raise ValueError("volume must be 0-100")
        self.request("ssap://audio/setVolume", {"volume": level})

    def volume_up(self) -> None:
        self.request("ssap://audio/volumeUp")

    def volume_down(self) -> None:
        self.request("ssap://audio/volumeDown")

    def set_mute(self, mute: bool = True) -> None:
        self.request("ssap://audio/setMute", {"mute": bool(mute)})

    def toggle_mute(self) -> bool:
        """Flip mute; returns the new state."""
        new_state = not self.muted
        self.set_mute(new_state)
        return new_state

    def get_sound_output(self) -> str:
        """e.g. 'tv_speaker', 'external_arc', 'bt_soundbar', 'headphone'."""
        payload = self.request(
            "ssap://com.webos.service.apiadapter/audio/getSoundOutput"
        )
        return payload.get("soundOutput", "")

    def set_sound_output(self, output: str) -> None:
        """Switch audio output, e.g. set_sound_output('external_arc')."""
        self.request("ssap://audio/changeSoundOutput", {"output": output})

    # ------------------------------------------------------------------ #
    # Apps
    # ------------------------------------------------------------------ #

    def list_apps(self) -> List[dict]:
        """All installed apps: [{'id': 'netflix', 'title': 'Netflix', ...}, ...]"""
        payload = self.request("ssap://com.webos.applicationManager/listApps")
        return payload.get("apps", [])

    def current_app(self) -> str:
        """App id of whatever is in the foreground (e.g. 'com.webos.app.hdmi2')."""
        payload = self.request(
            "ssap://com.webos.applicationManager/getForegroundAppInfo"
        )
        return payload.get("appId", "")

    def launch_app(self, app_id: str, params: Optional[dict] = None) -> dict:
        """Launch an app by id, e.g. 'netflix', 'youtube.leanback.v4', 'amazon'."""
        payload: dict = {"id": app_id}
        if params:
            payload["params"] = params
        return self.request("ssap://system.launcher/launch", payload)

    def close_app(self, app_id: str) -> None:
        self.request("ssap://system.launcher/close", {"id": app_id})

    def open_url(self, url: str) -> dict:
        """Open a URL in the TV's web browser."""
        return self.request("ssap://system.launcher/open", {"target": url})

    # ------------------------------------------------------------------ #
    # Inputs (HDMI etc.)
    # ------------------------------------------------------------------ #

    def list_inputs(self) -> List[dict]:
        """External inputs: [{'id': 'HDMI_1', 'label': 'PC', ...}, ...]"""
        payload = self.request("ssap://tv/getExternalInputList")
        return payload.get("devices", [])

    def set_input(self, input_id: str) -> None:
        """Switch input, e.g. set_input('HDMI_1')."""
        self.request("ssap://tv/switchInput", {"inputId": input_id})

    # ------------------------------------------------------------------ #
    # Live TV channels
    # ------------------------------------------------------------------ #

    def channel_up(self) -> None:
        self.request("ssap://tv/channelUp")

    def channel_down(self) -> None:
        self.request("ssap://tv/channelDown")

    def list_channels(self) -> List[dict]:
        payload = self.request("ssap://tv/getChannelList")
        return payload.get("channelList", [])

    def current_channel(self) -> dict:
        return self.request("ssap://tv/getCurrentChannel")

    def set_channel(self, channel: str) -> None:
        """Tune to a channel by number ('5') or channel id."""
        key = "channelNumber" if str(channel).isdigit() else "channelId"
        self.request("ssap://tv/openChannel", {key: str(channel)})

    # ------------------------------------------------------------------ #
    # Playback
    # ------------------------------------------------------------------ #

    def play(self) -> None:
        self.request("ssap://media.controls/play")

    def pause(self) -> None:
        self.request("ssap://media.controls/pause")

    def stop(self) -> None:
        self.request("ssap://media.controls/stop")

    def rewind(self) -> None:
        self.request("ssap://media.controls/rewind")

    def fast_forward(self) -> None:
        self.request("ssap://media.controls/fastForward")

    # ------------------------------------------------------------------ #
    # Remote buttons / pointer
    # ------------------------------------------------------------------ #

    def input_socket(self) -> PointerInputSocket:
        """The button/pointer socket (opened on demand, cached per session)."""
        if self._pointer is None or not self._pointer.connected:
            payload = self.request(
                "ssap://com.webos.service.networkinput/getPointerInputSocket"
            )
            path = payload.get("socketPath")
            if not path:
                raise LGTVError("TV did not return a pointer input socket path")
            self._pointer = PointerInputSocket(path)
        return self._pointer

    def button(self, name: str, repeat: int = 1) -> None:
        """Press a remote button (see ``lgtvpy.keys.BUTTONS``), e.g. tv.button('HOME')."""
        sock = self.input_socket()
        for _ in range(max(1, repeat)):
            sock.button(name)

    def click(self) -> None:
        self.input_socket().click()

    def move_pointer(self, dx: int, dy: int) -> None:
        self.input_socket().move(dx, dy)

    def scroll(self, dy: int) -> None:
        self.input_socket().scroll(dy)

    # ------------------------------------------------------------------ #
    # Text entry (into whatever field is focused on the TV)
    # ------------------------------------------------------------------ #

    def type_text(self, text: str) -> None:
        self.request(
            "ssap://com.webos.service.ime/insertText", {"text": text, "replace": 0}
        )

    def delete_chars(self, count: int = 1) -> None:
        self.request(
            "ssap://com.webos.service.ime/deleteCharacters", {"count": count}
        )

    def send_enter(self) -> None:
        self.request("ssap://com.webos.service.ime/sendEnterKey")

    # ------------------------------------------------------------------ #
    # Notifications
    # ------------------------------------------------------------------ #

    def notify(self, message: str, icon: Optional[str] = None) -> None:
        """Show a toast message on the TV."""
        payload: dict = {"message": message}
        if icon:
            payload["iconData"] = icon
            payload["iconExtension"] = "png"
        self.request("ssap://system.notifications/createToast", payload)

    # ------------------------------------------------------------------ #
    # System settings (picture, sound, and everything else)
    #
    # Reading uses the public settings API. *Writing* uses the Luna bridge:
    # the TV lets a paired client create an on-screen alert whose buttons may
    # call internal luna:// endpoints, so we create an invisible alert whose
    # every outcome applies the setting, then close it immediately. This is
    # the same mechanism bscpylgtv / Home Assistant use - unofficial but
    # long-standing, and it reaches every category and key.
    #
    # webOS 24+ also accepts writes through the public API
    # (set_system_settings), which reports errors but only covers a
    # subset of keys - see docs/SETTINGS.md.
    # ------------------------------------------------------------------ #

    def get_settings(self, category: str = "picture", keys: Optional[List[str]] = None) -> dict:
        """Read system settings, e.g. get_settings('picture', ['backlight'])."""
        payload = self.request(
            "ssap://settings/getSystemSettings",
            {"category": category, "keys": keys or PICTURE_KEYS},
        )
        return payload.get("settings", payload)

    def luna_request(self, luna_uri: str, params: dict) -> None:
        """Invoke an internal luna:// service via the alert-button bridge."""
        button = {"label": "", "onClick": luna_uri, "params": params}
        alert_payload = {
            "message": " ",
            "buttons": [button],
            "onclose": {"uri": luna_uri, "params": params},
            "onfail": {"uri": luna_uri, "params": params},
        }
        result = self.request(
            "ssap://system.notifications/createAlert", alert_payload
        )
        alert_id = result.get("alertId")
        if alert_id:
            # Closing fires "onclose", which applies the setting.
            self.request(
                "ssap://system.notifications/closeAlert", {"alertId": alert_id}
            )

    def set_settings(
        self, category: str, settings: dict, current_app: Optional[bool] = None
    ) -> None:
        """Write system settings, e.g. set_settings('picture', {'backlight': 30}).

        ``truMotionMode`` / ``aspectRatio`` are automatically sent in a
        separate write flagged ``current_app`` (the TV ignores them
        otherwise). Pass ``current_app`` to set the flag yourself.
        """
        for chunk, flag in _split_current_app(category, settings, current_app):
            params: dict = {"category": category, "settings": chunk}
            if flag is not None:
                params["current_app"] = flag
            self.luna_request(
                "luna://com.webos.settingsservice/setSystemSettings", params
            )

    def set_system_settings(
        self, category: str, settings: dict, current_app: Optional[bool] = None
    ) -> dict:
        """Write settings through the *public* settings API (webOS 24+).

        Unlike :meth:`set_settings` the TV answers, so a rejected key or
        value raises :class:`RequestError` instead of being silently ignored.
        Only a subset of keys is accepted this way (e.g. picture values and
        ``pictureMode``, but not ``soundMode``) - see docs/SETTINGS.md.
        """
        result: dict = {}
        for chunk, flag in _split_current_app(category, settings, current_app):
            payload: dict = {"category": category, "settings": chunk}
            if flag is not None:
                payload["current_app"] = flag
            result = self.request("ssap://settings/setSystemSettings", payload)
        return result

    # Convenience wrappers for the most common settings ------------------ #

    def get_picture_settings(self, keys: Optional[List[str]] = None) -> dict:
        return self.get_settings("picture", keys or PICTURE_KEYS)

    def set_picture_settings(self, settings: dict) -> None:
        """e.g. tv.set_picture_settings({'backlight': 40, 'contrast': 85})"""
        self.set_settings("picture", settings)

    def set_picture_mode(self, mode: str) -> None:
        """e.g. 'filmMaker', 'cinema', 'expert1', 'expert2', 'game', 'vivid',
        'normal', 'eco', 'sports', 'photo', 'personalized'. While HDR / Dolby
        Vision plays, the mode names differ ('hdrFilmMaker', 'dolbyHdrCinema',
        ...) - see docs/SETTINGS.md."""
        self.set_settings("picture", {"pictureMode": mode})

    def set_backlight(self, level: int) -> None:
        """OLED Light / backlight, 0-100."""
        if not 0 <= level <= 100:
            raise ValueError("backlight must be 0-100")
        self.set_settings("picture", {"backlight": level})

    def set_energy_saving(self, level: str) -> None:
        """'off', 'auto', 'min', 'med' or 'max'."""
        self.set_settings("picture", {"energySaving": level})

    def set_sound_mode(self, mode: str) -> None:
        """'aiSoundPlus', 'standard', 'movie', 'news', 'sports', 'music',
        'game' or 'bassBlast'."""
        self.set_settings("sound", {"soundMode": mode})

    # ------------------------------------------------------------------ #
    # Profiles (load a whole TV state from a TOML file)
    # ------------------------------------------------------------------ #

    def apply_profile(self, profile, dry_run: bool = False) -> List[str]:
        """Apply a settings profile - a path to a .toml file or a parsed dict.

        Returns the list of steps taken. See :mod:`lgtvpy.profiles`.
        """
        from . import profiles as _profiles

        if isinstance(profile, (str, Path)):
            profile = _profiles.load(profile)
        return _profiles.apply(self, profile, dry_run=dry_run)

    def capture_profile(self, name: Optional[str] = None) -> dict:
        """Read the current input/volume/picture/sound state into a profile dict."""
        from . import profiles as _profiles

        return _profiles.capture(self, name=name)

    # ------------------------------------------------------------------ #
    # Info / status
    # ------------------------------------------------------------------ #

    def system_info(self) -> dict:
        """Model name, serial number, receiver type etc.

        Newer firmware (webOS 25+) only answers ``getSystemInfo`` *before*
        registration, so the copy captured during the connection handshake
        is returned when the live call is refused. Falls back to
        :meth:`software_info` if neither is available.
        """
        try:
            return self.request("ssap://system/getSystemInfo")
        except RequestError:
            if self.client.system_info:
                return self.client.system_info
            return self.software_info()

    def software_info(self) -> dict:
        """Firmware details; 'device_id' is the TV's MAC address.

        Needs the signed pairing - refused (401) on webOS 26 firmware.
        """
        return self.request(
            "ssap://com.webos.service.update/getCurrentSWInformation"
        )

    def connection_info(self) -> dict:
        """Wired / Wi-Fi MAC addresses:
        {'wiredInfo': {'macAddress': ...}, 'wifiInfo': {'macAddress': ...}}"""
        return self.request("ssap://com.webos.service.connectionmanager/getinfo")

    def hello_info(self) -> dict:
        """What the TV announced when the connection opened: webOS version
        ('deviceOSReleaseVersion'), supported 'pairingTypes', etc."""
        return self.client.hello_info

    def status(self) -> dict:
        """One-call summary: power, app, volume, mute, sound output, input list."""
        summary: dict = {"ip": self.ip}
        probes = {
            "power": lambda: self.power_state().get("state"),
            "app": self.current_app,
            "volume": lambda: self.volume,
            "muted": lambda: self.muted,
            "sound_output": self.get_sound_output,
        }
        for name, probe in probes.items():
            try:
                summary[name] = probe()
            except (LGTVError, RequestError) as exc:
                summary[name] = f"<unavailable: {exc}>"
        return summary
