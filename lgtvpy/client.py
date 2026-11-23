"""Low-level SSAP (webOS "Second Screen" protocol) client.

Handles the WebSocket connection to the TV, the one-time pairing handshake,
request/response bookkeeping and the separate "pointer input" socket used for
remote-control button presses.

Most users should use the high-level :class:`lgtvpy.tv.LGTV` wrapper instead.
"""

from __future__ import annotations

import json
import ssl
import time
from collections import deque
from typing import Any, Callable, Optional, Tuple

import websocket  # pip package: websocket-client

SECURE_PORT = 3001  # wss - required on modern firmware (webOS 22+)
PLAIN_PORT = 3000  # ws  - legacy, often disabled on new TVs
PAIR_TIMEOUT = 60.0  # how long to wait for the user to press "Accept" on the TV
REQUEST_TIMEOUT = 10.0
CONNECT_TIMEOUT = 5.0
HANDSHAKE_TIMEOUT = 5.0  # pre-registration hello / system-info exchange

# Self-signed cert on the TV -> disable verification for the local connection.
_SSLOPT = {"cert_reqs": ssl.CERT_NONE, "check_hostname": False}


class LGTVError(Exception):
    """Base error for this package."""


class PairingError(LGTVError):
    """Pairing was rejected, timed out, or the stored key was revoked."""


class RequestError(LGTVError):
    """The TV answered a request with an error."""


class RequestTimeout(LGTVError):
    """No answer from the TV within the timeout."""


class _ImmediateRejection(PairingError):
    """The TV refused ``register`` outright, before showing any prompt."""


# ---------------------------------------------------------------------------
# Registration manifest
#
# This is LG's standard developer-sample manifest, used by every open-source
# webOS remote implementation. The signed blob + signature grant the client
# the full permission set (including WRITE_SETTINGS / WRITE_NOTIFICATION_ALERT,
# which are needed to change picture & system settings).
#
# webOS 26 firmware (43.x, mid-2026 onwards) blacklists this signing
# certificate and answers "403 Pairing rejected: blacklisted certificate
# detected". register() then retries with _UNSIGNED_MANIFEST (signature and
# signed block stripped, permissions merged) - the same fallback Home
# Assistant's aiowebostv uses. Pairing succeeds, but the TV only grants the
# unsigned permission tier: getCurrentSWInformation is refused, and on some
# models so are settings writes.
# ---------------------------------------------------------------------------
_SIGNATURE = (
    "eyJhbGdvcml0aG0iOiJSU0EtU0hBMjU2Iiwia2V5SWQiOiJ0ZXN0LXNpZ25pbmctY2VydCIsInNpZ25hdHVyZVZlcnNpb24iOjF9."
    "hrVRgjCwXVvE2OOSpDZ58hR+59aFNwYDyjQgKk3auukd7pcegmE2CzPCa0bJ0ZsRAcKkCTJrWo5iDzNhMBWRyaMOv5zWSrthlf7G"
    "128qvIlpMT0YNY+n/FaOHE73uLrS/g7swl3/qH/BGFG2Hu4RlL48eb3lLKqTt2xKHdCs6Cd4RMfJPYnzgvI4BNrFUKsjkcu+WD4O"
    "O2A27Pq1n50cMchmcaXadJhGrOqH5YmHdOCj5NSHzJYrsW0HPlpuAx/ECMeIZYDh6RMqaFM2DXzdKX9NmmyqzJ3o/0lkk/N97gfV"
    "RLW5hA29yeAwaCViZNCP8iC9aO0q9fQojoa7NQnAtw=="
)

_MANIFEST = {
    "manifestVersion": 1,
    "appVersion": "1.1",
    "signed": {
        "created": "20140509",
        "appId": "com.lge.test",
        "vendorId": "com.lge",
        "localizedAppNames": {
            "": "LG Remote App",
            "ko-KR": "리모컨 앱",
            "zxx-XX": "ЛГ Rэмotэ AПП",
        },
        "localizedVendorNames": {"": "LG Electronics"},
        "permissions": [
            "TEST_SECURE",
            "CONTROL_INPUT_TEXT",
            "CONTROL_MOUSE_AND_KEYBOARD",
            "READ_INSTALLED_APPS",
            "READ_LGE_SDX",
            "READ_NOTIFICATIONS",
            "SEARCH",
            "WRITE_SETTINGS",
            "WRITE_NOTIFICATION_ALERT",
            "CONTROL_POWER",
            "READ_CURRENT_CHANNEL",
            "READ_RUNNING_APPS",
            "READ_UPDATE_INFO",
            "UPDATE_FROM_REMOTE_APP",
            "READ_LGE_TV_INPUT_EVENTS",
            "READ_TV_CURRENT_TIME",
        ],
        "serial": "2f930e2d2cfe083771f68e4fe7bb07",
    },
    "permissions": [
        "LAUNCH",
        "LAUNCH_WEBAPP",
        "APP_TO_APP",
        "CLOSE",
        "TEST_OPEN",
        "TEST_PROTECTED",
        "CONTROL_AUDIO",
        "CONTROL_DISPLAY",
        "CONTROL_INPUT_JOYSTICK",
        "CONTROL_INPUT_MEDIA_RECORDING",
        "CONTROL_INPUT_MEDIA_PLAYBACK",
        "CONTROL_INPUT_TV",
        "CONTROL_POWER",
        "READ_APP_STATUS",
        "READ_CURRENT_CHANNEL",
        "READ_INPUT_DEVICE_LIST",
        "READ_NETWORK_STATE",
        "READ_RUNNING_APPS",
        "READ_TV_CHANNEL_LIST",
        "WRITE_NOTIFICATION_TOAST",
        "READ_POWER_STATE",
        "READ_COUNTRY_INFO",
        "READ_SETTINGS",
        "READ_TV_INFO",
        "CONTROL_TV_SCREEN",
        "CONTROL_TV_STANBY",
        "CONTROL_FAVORITE_GROUP",
        "CONTROL_USER_INFO",
        "CHECK_BLUETOOTH_DEVICE",
        "CONTROL_BLUETOOTH",
        "CONTROL_TIMER_INFO",
        "STB_INTERNAL_CONNECTION",
        "CONTROL_RECORDING",
        "READ_RECORDING_STATE",
        "WRITE_RECORDING_LIST",
        "READ_RECORDING_LIST",
        "READ_RECORDING_SCHEDULE",
        "WRITE_RECORDING_SCHEDULE",
        "READ_STORAGE_DEVICE_LIST",
        "READ_TV_PROGRAM_INFO",
        "CONTROL_BOX_CHANNEL",
        "READ_TV_ACR_AUTH_TOKEN",
        "READ_TV_CONTENT_STATE",
        "READ_TV_CURRENT_TIME",
        "ADD_LAUNCHER_CHANNEL",
        "SET_CHANNEL_SKIP",
        "RELEASE_CHANNEL_SKIP",
        "CONTROL_CHANNEL_BLOCK",
        "DELETE_SELECT_CHANNEL",
        "CONTROL_CHANNEL_GROUP",
        "SCAN_TV_CHANNELS",
        "CONTROL_TV_POWER",
        "CONTROL_WOL",
    ],
    "signatures": [{"signatureVersion": 1, "signature": _SIGNATURE}],
}

_UNSIGNED_MANIFEST = {
    "manifestVersion": _MANIFEST["manifestVersion"],
    "appVersion": _MANIFEST["appVersion"],
    "permissions": sorted(
        set(_MANIFEST["permissions"]) | set(_MANIFEST["signed"]["permissions"])
    ),
}


class WebOSClient:
    """Synchronous SSAP client for a single LG webOS TV."""

    def __init__(self, ip: str, timeout: float = REQUEST_TIMEOUT):
        self.ip = ip
        self.timeout = timeout
        self.url: Optional[str] = None
        self._ws: Optional[websocket.WebSocket] = None
        self._next_id = 0
        # Messages received while waiting for a different request id
        # (e.g. subscription pushes). Bounded so it can never grow unbounded.
        self._backlog: deque = deque(maxlen=100)
        # Filled by the pre-registration handshake (see register()).
        self.hello_info: dict = {}
        self.system_info: dict = {}
        # False once the TV has forced a reduced-permission (unsigned) pairing.
        self.signed_manifest = True

    # -- connection ---------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._ws is not None and self._ws.connected

    def connect(self, attempts: int = 3) -> None:
        """Open the WebSocket. Tries wss://:3001 first, then legacy ws://:3000.

        Retries briefly: the TV sometimes resets a connection that follows
        hot on the heels of a previous one.
        """
        last_error: Optional[Exception] = None
        for attempt in range(attempts):
            if attempt:
                time.sleep(0.8)
            for url in (
                f"wss://{self.ip}:{SECURE_PORT}",
                f"ws://{self.ip}:{PLAIN_PORT}",
            ):
                ws = websocket.WebSocket(sslopt=_SSLOPT)
                try:
                    # suppress_origin is required: webOS 24/25 firmware silently
                    # drops any session whose handshake carries an Origin header.
                    ws.connect(url, timeout=CONNECT_TIMEOUT, suppress_origin=True)
                except Exception as exc:  # noqa: BLE001 - report last failure below
                    last_error = exc
                    continue
                ws.settimeout(self.timeout)
                self._ws = ws
                self.url = url
                return
        raise LGTVError(
            f"Could not connect to TV at {self.ip} "
            f"(is it on and on the same network?): {last_error}"
        )

    def close(self) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            except Exception:  # noqa: BLE001 - best effort
                pass
            self._ws = None

    # -- pairing ------------------------------------------------------------

    def register(
        self,
        client_key: Optional[str] = None,
        timeout: float = PAIR_TIMEOUT,
        on_prompt: Optional[Callable[[], None]] = None,
    ) -> str:
        """Pair with the TV (or re-authenticate with a stored key).

        Without a ``client_key`` the TV shows an on-screen prompt that must be
        accepted with the remote; ``on_prompt`` is called when that happens.
        Returns the client key to store for future connections.

        Registers with the signed (full-permission) manifest first. If the TV
        refuses it outright - webOS 26 blacklists its certificate - pairing is
        retried with the unsigned manifest and :attr:`signed_manifest` becomes
        False.
        """
        self.handshake()
        try:
            key = self._register(client_key, timeout, on_prompt, _MANIFEST)
        except _ImmediateRejection:
            pass
        else:
            self.signed_manifest = True
            return key

        try:
            key = self._register(client_key, timeout, on_prompt, _UNSIGNED_MANIFEST)
        except PairingError:
            raise
        except LGTVError:
            # The TV hung up after rejecting the signature: use a fresh socket.
            self.close()
            self.connect()
            self.handshake()
            key = self._register(client_key, timeout, on_prompt, _UNSIGNED_MANIFEST)
        self.signed_manifest = False
        return key

    def handshake(self) -> None:
        """Pre-registration exchange: ``hello``, then ``getSystemInfo``.

        Newer firmware (webOS 25+) only answers ``getSystemInfo`` *before*
        registration, so the result is cached in :attr:`system_info`.
        ``hello`` reports the webOS version and supported pairing types
        (:attr:`hello_info`). Both are best effort - older firmware may
        refuse either, which is harmless.
        """
        try:
            self._send({"id": self._new_id(), "type": "hello", "payload": {}})
            msg = self._recv(timeout=HANDSHAKE_TIMEOUT)
            if msg.get("type") == "hello":
                self.hello_info = msg.get("payload", {})
            else:
                self._backlog.append(msg)
        except RequestTimeout:
            pass
        try:
            self.system_info = self.request(
                "ssap://system/getSystemInfo", timeout=HANDSHAKE_TIMEOUT
            )
        except (RequestError, RequestTimeout):
            pass

    def _register(
        self,
        client_key: Optional[str],
        timeout: float,
        on_prompt: Optional[Callable[[], None]],
        manifest: dict,
    ) -> str:
        payload: dict = {
            "forcePairing": False,
            "pairingType": "PROMPT",
            "manifest": manifest,
        }
        if client_key:
            payload["client-key"] = client_key

        self._send({"id": self._new_id(), "type": "register", "payload": payload})

        timed_out = PairingError(
            "Timed out waiting for pairing. Accept the prompt on the TV "
            "and try again."
        )
        deadline = time.monotonic() + timeout
        answered = False
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise timed_out
            try:
                msg = self._recv(timeout=remaining)
            except RequestTimeout:
                raise timed_out from None
            msg_type = msg.get("type")
            if msg_type == "registered":
                key = msg.get("payload", {}).get("client-key") or client_key
                if not key:
                    raise PairingError("TV completed pairing but sent no client key")
                return key
            if msg_type == "response":
                # TV acknowledged and is now showing the pairing prompt.
                answered = True
                if msg.get("payload", {}).get("pairingType") == "PROMPT" and on_prompt:
                    on_prompt()
                continue
            if msg_type == "error":
                # An error *after* the prompt means the user declined or it
                # timed out - never retry that, it would prompt them again.
                error_cls = PairingError if answered else _ImmediateRejection
                raise error_cls(f"TV rejected pairing: {msg.get('error')}")

    # -- requests -----------------------------------------------------------

    def request(
        self,
        uri: str,
        payload: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> dict:
        """Send an ssap:// request and return the response payload."""
        req_id = self._new_id()
        self._send(
            {"id": req_id, "type": "request", "uri": uri, "payload": payload or {}}
        )
        return self._wait_for(req_id, uri, timeout or self.timeout)

    def subscribe(
        self,
        uri: str,
        payload: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> Tuple[str, dict]:
        """Subscribe to a status URI.

        Returns ``(subscription_id, current_state)``. Further updates arrive
        via :meth:`next_event` / :meth:`events`.
        """
        sub_id = self._new_id()
        self._send(
            {"id": sub_id, "type": "subscribe", "uri": uri, "payload": payload or {}}
        )
        first = self._wait_for(sub_id, uri, timeout or self.timeout)
        return sub_id, first

    def next_event(self, timeout: float = 30.0) -> Optional[Tuple[str, dict]]:
        """Return the next ``(subscription_id, payload)`` push, or None on timeout."""
        if self._backlog:
            msg = self._backlog.popleft()
            return str(msg.get("id")), msg.get("payload", {})
        try:
            msg = self._recv(timeout=timeout)
        except RequestTimeout:
            return None
        return str(msg.get("id")), msg.get("payload", {})

    def events(self, timeout: float = 30.0):
        """Generator yielding subscription events until a timeout occurs."""
        while True:
            event = self.next_event(timeout=timeout)
            if event is None:
                return
            yield event

    # -- internals ----------------------------------------------------------

    def _new_id(self) -> str:
        self._next_id += 1
        return str(self._next_id)

    def _send(self, obj: dict) -> None:
        if not self.connected:
            raise LGTVError("Not connected - call connect() first")
        assert self._ws is not None
        try:
            self._ws.send(json.dumps(obj))
        except (websocket.WebSocketConnectionClosedException, OSError) as exc:
            self.close()
            raise LGTVError(f"Connection to TV lost: {exc}") from exc

    def _recv(self, timeout: float) -> dict:
        assert self._ws is not None
        self._ws.settimeout(max(timeout, 0.1))
        try:
            raw = self._ws.recv()
        except websocket.WebSocketTimeoutException as exc:
            raise RequestTimeout(f"No response from TV within {timeout:.0f}s") from exc
        except (websocket.WebSocketConnectionClosedException, OSError) as exc:
            self.close()
            raise LGTVError(f"Connection to TV lost: {exc}") from exc
        finally:
            if self._ws is not None:
                self._ws.settimeout(self.timeout)
        if not raw:
            raise LGTVError("Connection to TV closed")
        return json.loads(raw)

    def _wait_for(self, req_id: str, uri: str, timeout: float) -> dict:
        """Read frames until the response for ``req_id`` arrives."""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RequestTimeout(f"{uri}: no response within {timeout:.0f}s")
            msg = self._recv(timeout=remaining)
            if str(msg.get("id")) != req_id:
                self._backlog.append(msg)  # subscription push for someone else
                continue
            if msg.get("type") == "error":
                raise RequestError(f"{uri}: {msg.get('error', 'unknown error')}")
            payload = msg.get("payload", {})
            if payload.get("returnValue") is False:
                raise RequestError(
                    f"{uri}: {payload.get('errorText', payload)}"
                )
            return payload


class PointerInputSocket:
    """Secondary WebSocket used for remote-control buttons & pointer moves.

    Obtain via :meth:`lgtvpy.tv.LGTV.input_socket` - the URL comes from the
    ``getPointerInputSocket`` SSAP call and is only valid for the current
    session.
    """

    def __init__(self, url: str):
        self._ws = websocket.WebSocket(sslopt=_SSLOPT)
        self._ws.connect(url, timeout=CONNECT_TIMEOUT, suppress_origin=True)

    @property
    def connected(self) -> bool:
        return self._ws.connected

    def button(self, name: str) -> None:
        """Press a remote button, e.g. ``HOME``, ``UP``, ``ENTER`` (see lgtvpy.keys)."""
        self._send(type="button", name=name.upper())

    def click(self) -> None:
        """Click at the current pointer position (like pressing the wheel)."""
        self._send(type="click")

    def move(self, dx: int, dy: int, drag: bool = False) -> None:
        """Move the on-screen pointer by a relative amount."""
        self._send(type="move", dx=dx, dy=dy, down=1 if drag else 0)

    def scroll(self, dy: int) -> None:
        """Scroll (positive = up, like a mouse wheel)."""
        self._send(type="scroll", dx=0, dy=dy)

    def close(self) -> None:
        try:
            self._ws.close()
        except Exception:  # noqa: BLE001 - best effort
            pass

    def _send(self, **fields: Any) -> None:
        # Wire format is newline-separated key:value pairs, blank-line terminated:
        #   type:button\nname:HOME\n\n
        msg_type = fields.pop("type")
        lines = [f"type:{msg_type}"] + [f"{k}:{v}" for k, v in fields.items()]
        self._ws.send("\n".join(lines) + "\n\n")
