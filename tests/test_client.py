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


def test_register_prompt_never_answered_is_pairing_timeout(fake_tv):
    import json

    original_receive = fake_tv.receive

    def receive(raw):
        msg = json.loads(raw)
        if msg.get("type") == "register":  # prompt shown, user never answers
            return [{"type": "response", "id": msg["id"],
                     "payload": {"pairingType": "PROMPT"}}]
        return original_receive(raw)

    fake_tv.receive = receive
    client = make_client(fake_tv)
    with pytest.raises(PairingError, match="Timed out"):
        client.register()
    assert len(fake_tv.sockets) == 1  # no unsigned retry / reconnect


# -- pre-registration handshake ---------------------------------------------


def test_register_does_hello_and_system_info_first(fake_tv):
    fake_tv.routes["ssap://system/getSystemInfo"] = {
        "returnValue": True,
        "modelName": "OLED42C34LA",
    }
    client = make_client(fake_tv)
    client.register("test-client-key")
    assert client.hello_info["deviceOSReleaseVersion"] == "10.2.0"
    assert client.system_info["modelName"] == "OLED42C34LA"

    import json
    sent = [json.loads(raw) for raw in fake_tv.sockets[0].sent]
    assert [m["type"] for m in sent] == ["hello", "request", "register"]
    assert sent[1]["uri"] == "ssap://system/getSystemInfo"


def test_handshake_is_best_effort(fake_tv):
    fake_tv.hello = None  # TV ignores hello
    fake_tv.routes["ssap://system/getSystemInfo"] = {
        "returnValue": False,
        "errorText": "401 insufficient permissions (not registered)",
    }
    client = make_client(fake_tv)
    assert client.register("test-client-key") == "test-client-key"
    assert client.hello_info == {}
    assert client.system_info == {}


# -- webOS 26: blacklisted signing certificate -------------------------------


def test_signed_manifest_is_used_when_accepted(fake_tv):
    client = make_client(fake_tv)
    client.register()
    assert client.signed_manifest
    assert len(fake_tv.registrations) == 1
    assert "signatures" in fake_tv.registrations[0]


def test_rejected_signature_retries_unsigned_on_same_socket(fake_tv):
    fake_tv.reject_signed = True
    client = make_client(fake_tv)
    prompts = []
    key = client.register(on_prompt=lambda: prompts.append(1))

    assert key == "test-client-key"
    assert client.signed_manifest is False
    assert prompts == [1]  # only the unsigned attempt prompts
    assert len(fake_tv.sockets) == 1
    signed, unsigned = fake_tv.registrations
    assert "signatures" in signed
    assert set(unsigned) == {"manifestVersion", "appVersion", "permissions"}
    # The signed tier's permissions are still requested, just unsigned.
    assert "WRITE_SETTINGS" in unsigned["permissions"]
    assert "CONTROL_MOUSE_AND_KEYBOARD" in unsigned["permissions"]
    assert unsigned["permissions"] == sorted(set(unsigned["permissions"]))


def test_rejected_signature_with_stored_key_keeps_key(fake_tv):
    fake_tv.reject_signed = True
    client = make_client(fake_tv)
    prompts = []
    key = client.register("test-client-key", on_prompt=lambda: prompts.append(1))
    assert key == "test-client-key"
    assert prompts == []
    assert client.signed_manifest is False


def test_declined_prompt_is_not_retried_unsigned(fake_tv):
    fake_tv.reject_pairing = True
    client = make_client(fake_tv)
    prompts = []
    with pytest.raises(PairingError, match="denied"):
        client.register(on_prompt=lambda: prompts.append(1))
    assert prompts == [1]  # the user is not asked a second time
    assert len(fake_tv.registrations) == 1


def test_unsigned_also_rejected_raises_and_stays_signed(fake_tv):
    import json

    original_receive = fake_tv.receive

    def receive(raw):
        msg = json.loads(raw)
        if msg.get("type") == "register":
            fake_tv.registrations.append(msg["payload"]["manifest"])
            return [{"type": "error", "id": msg["id"], "error": "500 booting"}]
        return original_receive(raw)

    fake_tv.receive = receive
    client = make_client(fake_tv)
    with pytest.raises(PairingError, match="booting"):
        client.register("test-client-key")
    assert len(fake_tv.registrations) == 2
    assert client.signed_manifest  # a failed fallback isn't remembered


def test_reconnects_if_tv_hangs_up_after_rejecting_signature(fake_tv):
    fake_tv.reject_signed = True
    client = make_client(fake_tv)
    first_ws = fake_tv.sockets[0]
    original_recv = first_ws.recv

    def recv_then_hang_up():
        frame = original_recv()
        if "blacklisted" in frame:
            first_ws.connected = False
        return frame

    first_ws.recv = recv_then_hang_up
    assert client.register() == "test-client-key"
    assert client.signed_manifest is False
    assert len(fake_tv.sockets) == 2
    assert "signatures" not in fake_tv.registrations[-1]


def test_send_on_dropped_socket_raises_lgtv_error(fake_tv):
    client = make_client(fake_tv)
    ws = fake_tv.sockets[0]

    def broken_send(raw):
        raise ConnectionResetError("reset by peer")

    ws.send = broken_send
    with pytest.raises(LGTVError, match="Connection to TV lost"):
        client.request("ssap://audio/getVolume")
    assert not client.connected


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
