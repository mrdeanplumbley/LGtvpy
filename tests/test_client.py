"""WebOSClient protocol tests against the scripted FakeTV (no network)."""

import pytest

from lgtvpy.client import (
    LGTVError,
    PairingError,
    RequestError,
    RequestTimeout,
    WebOSClient,
)


def make_client(fake_tv, **kwargs):
    client = WebOSClient("192.0.2.1", **kwargs)
    client.connect()
    return client


# -- connection -------------------------------------------------------------


def test_connect_prefers_secure_port(fake_tv):
    client = make_client(fake_tv)
    assert client.url == "wss://192.0.2.1:3001"
    assert client.connected


def test_connect_suppresses_origin_header(fake_tv):
    # webOS 24/25 silently drops sessions that carry an Origin header.
    make_client(fake_tv)
    assert fake_tv.sockets[0].connect_kwargs.get("suppress_origin") is True


def test_connect_falls_back_to_plain_port(fake_tv):
    fake_tv.fail_urls = ("wss://",)
    client = make_client(fake_tv)
    assert client.url == "ws://192.0.2.1:3000"


def test_connect_retries_then_raises(fake_tv):
    fake_tv.fail_urls = ("wss://", "ws://")
    with pytest.raises(LGTVError, match="Could not connect"):
        WebOSClient("192.0.2.1").connect()
    # 3 attempts x 2 urls
    assert len(fake_tv.sockets) == 6


def test_send_before_connect_raises():
    with pytest.raises(LGTVError, match="Not connected"):
        WebOSClient("192.0.2.1").request("ssap://audio/getVolume")


# -- pairing ----------------------------------------------------------------


def test_register_first_time_prompts_and_returns_key(fake_tv):
    client = make_client(fake_tv)
    prompts = []
    key = client.register(on_prompt=lambda: prompts.append(1))
    assert key == "test-client-key"
    assert prompts == [1]


def test_register_with_stored_key_skips_prompt(fake_tv):
    client = make_client(fake_tv)
    prompts = []
    key = client.register("test-client-key", on_prompt=lambda: prompts.append(1))
    assert key == "test-client-key"
    assert prompts == []


def test_register_rejection_raises_pairing_error(fake_tv):
    fake_tv.reject_pairing = True
    client = make_client(fake_tv)
    with pytest.raises(PairingError, match="rejected"):
        client.register()


def test_register_zero_timeout_raises_pairing_error(fake_tv):
    client = make_client(fake_tv)
    with pytest.raises(PairingError, match="Timed out"):
        client.register(timeout=0)


# -- requests ---------------------------------------------------------------


def test_request_returns_payload(fake_tv):
    fake_tv.routes["ssap://audio/getVolume"] = {"returnValue": True, "volume": 7}
    client = make_client(fake_tv)
    assert client.request("ssap://audio/getVolume")["volume"] == 7


def test_request_error_frame_raises(fake_tv):
    import json

    client = make_client(fake_tv)
    original_receive = fake_tv.receive

    def receive(raw):
        msg = json.loads(raw)
        if msg.get("uri") == "ssap://x":
            return [{
                "type": "error", "id": msg["id"],
                "error": "401 insufficient permissions",
            }]
        return original_receive(raw)

    fake_tv.receive = receive
    with pytest.raises(RequestError, match="401"):
        client.request("ssap://x")


def test_request_return_value_false_raises(fake_tv):
    fake_tv.routes["ssap://tv/switchInput"] = {
        "returnValue": False,
        "errorText": "no such input",
    }
    client = make_client(fake_tv)
    with pytest.raises(RequestError, match="no such input"):
        client.request("ssap://tv/switchInput", {"inputId": "HDMI_9"})


def test_request_timeout(fake_tv):
    fake_tv.routes["ssap://slow"] = None  # TV never answers
    client = make_client(fake_tv, timeout=0.05)
    with pytest.raises(RequestTimeout):
        client.request("ssap://slow")


def test_request_ids_increment_and_match(fake_tv):
    seen_ids = []

    def route(msg):
        seen_ids.append(msg["id"])
        return {"returnValue": True}

    fake_tv.routes["ssap://a"] = route
    client = make_client(fake_tv)
    client.request("ssap://a")
    client.request("ssap://a")
    assert seen_ids == ["1", "2"]


# -- subscriptions ----------------------------------------------------------


def test_subscription_pushes_go_to_backlog(fake_tv):
    fake_tv.routes["ssap://audio/getVolume"] = {"returnValue": True, "volume": 5}
    client = make_client(fake_tv)
    sub_id, first = client.subscribe("ssap://audio/getVolume")
    assert first["volume"] == 5

    # A push for the subscription arrives while another request is in flight.
    fake_tv.pushes.append(
        {"type": "response", "id": sub_id, "payload": {"volume": 6}}
    )
    fake_tv.routes["ssap://other"] = {"returnValue": True}
    client.request("ssap://other")  # push gets buffered, request still matches

    event = client.next_event(timeout=0.05)
    assert event == (sub_id, {"volume": 6})
    assert client.next_event(timeout=0.05) is None  # nothing else queued


# -- pointer input socket ---------------------------------------------------


def test_pointer_socket_wire_format(fake_tv):
    from lgtvpy.client import PointerInputSocket

    sock = PointerInputSocket("wss://192.0.2.1:3001/resources/x/netinput.pointer")
    sock.button("home")
    sock.click()
    sock.move(5, -3)
    sock.scroll(1)
    ws = fake_tv.sockets[-1]
    assert ws.sent == [
        "type:button\nname:HOME\n\n",
        "type:click\n\n",
        "type:move\ndx:5\ndy:-3\ndown:0\n\n",
        "type:scroll\ndx:0\ndy:1\n\n",
    ]
