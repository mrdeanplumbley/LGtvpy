"""Shared test fakes.

Two levels of fake are provided:

- ``fake_tv`` (fixture): patches ``websocket.WebSocket`` inside ``lgtvpy.client``
  with an in-memory socket wired to a scripted :class:`FakeTV` that speaks the
  SSAP protocol (register handshake, request/response ids, subscription
  pushes). Used to test the real ``WebOSClient`` end to end without a network.

- :class:`StubClient`: a recording stand-in for ``WebOSClient`` injected into
  ``LGTV`` to test that high-level methods hit the right URIs with the right
  payloads.
"""

from __future__ import annotations

import json

import pytest
import websocket as websocket_lib

from lgtvpy import client as client_mod


class FakeTV:
    """Scripted 'TV side' of the connection.

    ``routes`` maps ssap uris to a response payload dict, a callable
    ``(msg) -> payload``, or ``None`` to simulate no answer (timeout).
    ``pushes`` are extra frames (e.g. subscription updates) delivered before
    the next response.
    """

    def __init__(self):
        self.client_key = "test-client-key"
        self.reject_pairing = False   # user declines the on-screen prompt
        self.reject_signed = False    # webOS 26: signed manifest blacklisted
        self.hello = {"deviceOSReleaseVersion": "10.2.0", "pairingTypes": ["PROMPT"]}
        self.routes = {}
        self.pushes = []
        self.registrations = []  # manifests received, in order
        self.fail_urls = ()  # url fragments whose connect attempts get "reset"
        self.sockets = []    # every FakeWebSocket created

    def receive(self, raw: str) -> list:
        msg = json.loads(raw)
        mtype = msg.get("type")
        out = []
        if mtype == "hello":
            if self.hello is None:
                return []
            return [{"type": "hello", "payload": self.hello}]  # no id, like the TV
        if mtype == "register":
            manifest = msg["payload"]["manifest"]
            self.registrations.append(manifest)
            if self.reject_signed and "signatures" in manifest:
                return [{
                    "type": "error", "id": msg["id"],
                    "error": "403 Pairing rejected: blacklisted certificate detected",
                }]
            supplied = msg["payload"].get("client-key")
            if self.reject_pairing:
                # Declining happens on screen, i.e. after the prompt is shown.
                return [
                    {"type": "response", "id": msg["id"],
                     "payload": {"pairingType": "PROMPT", "returnValue": True}},
                    {"type": "error", "id": msg["id"], "error": "403 User denied access"},
                ]
            if supplied != self.client_key:
                # Unknown key -> TV shows the pairing prompt first.
                out.append({
                    "type": "response", "id": msg["id"],
                    "payload": {"pairingType": "PROMPT", "returnValue": True},
                })
            out.append({
                "type": "registered", "id": msg["id"],
                "payload": {"client-key": self.client_key},
            })
            return out
        if mtype in ("request", "subscribe"):
            route = self.routes.get(msg["uri"], {"returnValue": True})
            if route is None:
                return []
            payload = route(msg) if callable(route) else route
            out.extend(self.pushes)
            self.pushes = []
            out.append({"type": "response", "id": msg["id"], "payload": payload})
            return out
        return []


class FakeWebSocket:
    """Duck-typed replacement for ``websocket.WebSocket``."""

    def __init__(self, tv: FakeTV, sslopt=None):
        self.tv = tv
        self.sslopt = sslopt
        self.connected = False
        self.url = None
        self.connect_kwargs = None
        self.sent = []
        self.queue = []

    def connect(self, url, **kwargs):
        self.connect_kwargs = kwargs
        for fragment in self.tv.fail_urls:
            if fragment in url:
                raise ConnectionResetError(f"connection reset: {url}")
        self.url = url
        self.connected = True

    def settimeout(self, value):
        pass

    def send(self, raw):
        if not self.connected:
            raise websocket_lib.WebSocketConnectionClosedException("closed")
        self.sent.append(raw)
        # JSON frames go to the scripted TV; pointer-socket frames are
        # plain "key:value" text and just get recorded.
        if raw.lstrip().startswith("{"):
            self.queue.extend(json.dumps(frame) for frame in self.tv.receive(raw))

    def recv(self):
        if not self.connected:
            raise websocket_lib.WebSocketConnectionClosedException("closed")
        if self.queue:
            return self.queue.pop(0)
        raise websocket_lib.WebSocketTimeoutException("no frames queued")

    def close(self):
        self.connected = False


@pytest.fixture
def fake_tv(monkeypatch):
    """Patch lgtvpy.client to talk to a scripted FakeTV instead of a network."""
    tv = FakeTV()

    def factory(sslopt=None):
        ws = FakeWebSocket(tv, sslopt=sslopt)
        tv.sockets.append(ws)
        return ws

    monkeypatch.setattr(client_mod.websocket, "WebSocket", factory)
    monkeypatch.setattr(client_mod.time, "sleep", lambda seconds: None)
    return tv


class StubClient:
    """Recording stand-in for WebOSClient, injected into LGTV as ``_client``.

    ``responses`` maps uri -> payload dict, callable(payload) -> dict, or an
    Exception instance to raise.
    """

    def __init__(self, responses=None):
        self.connected = True
        self.calls = []
        self.responses = responses or {}
        self.signed_manifest = True
        self.hello_info = {}
        self.system_info = {}

    def request(self, uri, payload=None, timeout=None):
        self.calls.append((uri, payload))
        result = self.responses.get(uri, {"returnValue": True})
        if isinstance(result, Exception):
            raise result
        if callable(result):
            return result(payload)
        return result

    def uris(self):
        return [uri for uri, _ in self.calls]

    def close(self):
        self.connected = False


@pytest.fixture
def stub_tv(tmp_path):
    """An LGTV wired to a StubClient (no pairing, no network)."""
    from lgtvpy.tv import LGTV

    tv = LGTV("192.0.2.1", config_path=tmp_path / "config.json")
    tv._client = StubClient()
    return tv
