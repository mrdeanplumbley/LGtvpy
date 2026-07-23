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
from typing import Callable, List, Optional

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
        return self.client.request(uri, payload)

    def _remember_mac(self) -> None:
        """Store the TV's MAC (needed for Wake-on-LAN power-on) if unknown."""
        if _config.get_tv(self.ip, self._config_path).get("mac"):
            return
        try:
            info = self.software_info()
            mac = info.get("device_id")  # webOS reports its MAC here
            if mac:
                _config.update_tv(self.ip, self._config_path, mac=mac)
        except LGTVError:
            pass  # non-fatal; power_on() will explain if the MAC is missing

    # ------------------------------------------------------------------ #
    # Power
    # ------------------------------------------------------------------ #

    def power_off(self) -> None:
        """Put the TV into standby."""
        self.request("ssap://system/turnOff")

    def power_on(self, mac: Optional[str] = None) -> None:
        """Wake the TV via Wake-on-LAN (works without a live connection).

        Uses the MAC stored during pairing unless one is passed. Requires
        the TV's "Turn On via Wi-Fi" / Quick Start+ setting to be enabled.
        """
        mac = mac or _config.get_tv(self.ip, self._config_path).get("mac")
        if not mac:
            raise LGTVError(
                "No MAC address known for this TV. Connect once while it is on "
                "(so it can be auto-detected) or pass mac='aa:bb:cc:dd:ee:ff'."
            )
        send_magic_packet(mac)

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
    # long-standing.
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

    def set_settings(self, category: str, settings: dict) -> None:
        """Write system settings, e.g. set_settings('picture', {'backlight': 30})."""
        self.luna_request(
            "luna://com.webos.settingsservice/setSystemSettings",
            {"category": category, "settings": settings},
        )

    # Convenience wrappers for the most common settings ------------------ #

    def get_picture_settings(self, keys: Optional[List[str]] = None) -> dict:
        return self.get_settings("picture", keys or PICTURE_KEYS)

    def set_picture_settings(self, settings: dict) -> None:
        """e.g. tv.set_picture_settings({'backlight': 40, 'contrast': 85})"""
        self.set_settings("picture", settings)

    def set_picture_mode(self, mode: str) -> None:
        """e.g. 'cinema', 'filmMaker', 'game', 'expert1', 'vivid', 'normal'."""
        self.set_settings("picture", {"pictureMode": mode})

    def set_backlight(self, level: int) -> None:
        """OLED Light / backlight, 0-100."""
        if not 0 <= level <= 100:
            raise ValueError("backlight must be 0-100")
        self.set_settings("picture", {"backlight": level})

    def set_energy_saving(self, level: str) -> None:
        """e.g. 'off', 'min', 'med', 'max', 'auto', 'screen_off'."""
        self.set_settings("picture", {"energySaving": level})

    def set_sound_mode(self, mode: str) -> None:
        """e.g. 'aiSoundPlus', 'standard', 'movie', 'music', 'game', 'sports'."""
        self.set_settings("sound", {"soundMode": mode})

    # ------------------------------------------------------------------ #
    # Info / status
    # ------------------------------------------------------------------ #

    def system_info(self) -> dict:
        """Model name, firmware branch etc.

        Newer firmware (webOS 25) blocks ``getSystemInfo`` for third-party
        clients, so this falls back to :meth:`software_info` there.
        """
        try:
            return self.request("ssap://system/getSystemInfo")
        except RequestError:
            return self.software_info()

    def software_info(self) -> dict:
        """Firmware details; 'device_id' is the TV's MAC address."""
        return self.request(
            "ssap://com.webos.service.update/getCurrentSWInformation"
        )

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
