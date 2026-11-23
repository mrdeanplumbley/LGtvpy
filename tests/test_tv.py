"""High-level LGTV API tests: correct URIs/payloads via StubClient, plus the
full connect/pair flow against the FakeTV."""

import pytest

from lgtvpy import LGTV, config
from lgtvpy.client import LGTVError, RequestError
from tests.conftest import StubClient


# -- IP resolution ----------------------------------------------------------


def test_no_ip_and_no_paired_tv_raises(tmp_path):
    with pytest.raises(LGTVError, match="No TV IP"):
        LGTV(config_path=tmp_path / "config.json")


def test_no_ip_resolves_single_paired_tv(tmp_path):
    cfg = tmp_path / "config.json"
    config.update_tv("10.0.0.7", cfg, client_key="k")
    assert LGTV(config_path=cfg).ip == "10.0.0.7"


def test_no_ip_with_multiple_paired_tvs_raises(tmp_path):
    cfg = tmp_path / "config.json"
    config.update_tv("10.0.0.7", cfg, client_key="k1")
    config.update_tv("10.0.0.8", cfg, client_key="k2")
    with pytest.raises(LGTVError):
        LGTV(config_path=cfg)


def test_explicit_ip_wins(tmp_path):
    cfg = tmp_path / "config.json"
    config.update_tv("10.0.0.7", cfg, client_key="k")
    assert LGTV("10.0.0.9", config_path=cfg).ip == "10.0.0.9"


# -- connect / pairing flow (real WebOSClient + FakeTV) ---------------------


def test_connect_pairs_and_stores_key_and_mac(fake_tv, tmp_path):
    cfg = tmp_path / "config.json"
    fake_tv.routes["ssap://com.webos.service.update/getCurrentSWInformation"] = {
        "returnValue": True,
        "device_id": "aa:bb:cc:dd:ee:ff",
    }
    prompts = []
    tv = LGTV("10.0.0.9", config_path=cfg, on_pair_prompt=lambda: prompts.append(1))
    tv.connect()
    tv.close()

    stored = config.get_tv("10.0.0.9", cfg)
    assert stored["client_key"] == "test-client-key"
    assert stored["mac"] == "aa:bb:cc:dd:ee:ff"
    assert prompts == [1]


def test_second_connect_reuses_key_without_prompt(fake_tv, tmp_path):
    cfg = tmp_path / "config.json"
    fake_tv.routes["ssap://com.webos.service.update/getCurrentSWInformation"] = {
        "returnValue": True,
        "device_id": "aa:bb:cc:dd:ee:ff",
    }
    LGTV("10.0.0.9", config_path=cfg).connect().close()

    prompts = []
    tv = LGTV("10.0.0.9", config_path=cfg, on_pair_prompt=lambda: prompts.append(1))
    tv.connect()
    tv.close()
    assert prompts == []


# -- volume -----------------------------------------------------------------


def test_volume_parses_nested_webos22_payload(stub_tv):
    stub_tv._client.responses["ssap://audio/getVolume"] = {
        "returnValue": True,
        "volumeStatus": {"volume": 17, "muteStatus": True},
    }
    assert stub_tv.volume == 17
    assert stub_tv.muted is True


def test_volume_parses_flat_legacy_payload(stub_tv):
    stub_tv._client.responses["ssap://audio/getVolume"] = {
        "returnValue": True,
        "volume": 9,
        "muted": False,
    }
    assert stub_tv.volume == 9
    assert stub_tv.muted is False


def test_set_volume_sends_payload_and_validates_range(stub_tv):
    stub_tv.set_volume(30)
    assert ("ssap://audio/setVolume", {"volume": 30}) in stub_tv._client.calls
    with pytest.raises(ValueError):
        stub_tv.set_volume(101)
    with pytest.raises(ValueError):
        stub_tv.set_volume(-1)


def test_toggle_mute_flips_current_state(stub_tv):
    stub_tv._client.responses["ssap://audio/getVolume"] = {
        "volumeStatus": {"volume": 5, "muteStatus": False}
    }
    assert stub_tv.toggle_mute() is True
    assert ("ssap://audio/setMute", {"mute": True}) in stub_tv._client.calls


# -- settings via the Luna bridge -------------------------------------------


def test_set_settings_uses_alert_bridge(stub_tv):
    stub = stub_tv._client
    stub.responses["ssap://system.notifications/createAlert"] = {
        "returnValue": True,
        "alertId": "alert-42",
    }
    stub_tv.set_settings("picture", {"backlight": 40})

    create_uri, create_payload = stub.calls[0]
    assert create_uri == "ssap://system.notifications/createAlert"
    button = create_payload["buttons"][0]
    assert button["onClick"] == "luna://com.webos.settingsservice/setSystemSettings"
    assert button["params"] == {"category": "picture", "settings": {"backlight": 40}}
    assert create_payload["onclose"]["params"] == button["params"]

    assert stub.calls[1] == (
        "ssap://system.notifications/closeAlert",
        {"alertId": "alert-42"},
    )


def _luna_params(stub):
    return [
        payload["buttons"][0]["params"]
        for uri, payload in stub.calls
        if uri == "ssap://system.notifications/createAlert"
    ]


def test_set_settings_sends_trumotion_flagged_current_app(stub_tv):
    # The TV ignores truMotionMode unless the write carries current_app.
    stub_tv.set_settings(
        "picture", {"backlight": 40, "truMotionMode": "off", "contrast": 85}
    )
    assert _luna_params(stub_tv._client) == [
        {"category": "picture", "settings": {"backlight": 40, "contrast": 85}},
        {"category": "picture", "settings": {"truMotionMode": "off"},
         "current_app": True},
    ]


def test_set_settings_trumotion_alone_is_one_flagged_call(stub_tv):
    stub_tv.set_settings("picture", {"truMotionMode": "cinemaClear"})
    assert _luna_params(stub_tv._client) == [
        {"category": "picture", "settings": {"truMotionMode": "cinemaClear"},
         "current_app": True},
    ]


def test_set_settings_explicit_current_app_covers_whole_write(stub_tv):
    stub_tv.set_settings("picture", {"truMotionMode": "off", "backlight": 1},
                         current_app=False)
    assert _luna_params(stub_tv._client) == [
        {"category": "picture",
         "settings": {"truMotionMode": "off", "backlight": 1},
         "current_app": False},
    ]


def test_set_settings_other_categories_never_split(stub_tv):
    stub_tv.set_settings("other", {"truMotionMode": "x", "enableALLM": "on"})
    assert len(_luna_params(stub_tv._client)) == 1


def test_set_system_settings_uses_public_api(stub_tv):
    stub_tv.set_system_settings("picture", {"pictureMode": "expert2"})
    stub_tv.set_system_settings("picture", {"truMotionMode": "off"})
    assert stub_tv._client.calls == [
        ("ssap://settings/setSystemSettings",
         {"category": "picture", "settings": {"pictureMode": "expert2"}}),
        ("ssap://settings/setSystemSettings",
         {"category": "picture", "settings": {"truMotionMode": "off"},
          "current_app": True}),
    ]


def test_set_system_settings_surfaces_rejection(stub_tv):
    stub_tv._client.responses["ssap://settings/setSystemSettings"] = RequestError(
        "ssap://settings/setSystemSettings: Some keys are not allowed"
    )
    with pytest.raises(RequestError, match="not allowed"):
        stub_tv.set_system_settings("sound", {"soundMode": "movie"})


def test_401_on_unsigned_pairing_explains_why(stub_tv):
    stub_tv._client.signed_manifest = False
    stub_tv._client.responses["ssap://x"] = RequestError("ssap://x: 401 insufficient permissions")
    with pytest.raises(RequestError, match="reduced-permission pairing"):
        stub_tv.request("ssap://x")


def test_401_on_signed_pairing_is_unchanged(stub_tv):
    stub_tv._client.responses["ssap://x"] = RequestError("ssap://x: 401 insufficient permissions")
    with pytest.raises(RequestError) as info:
        stub_tv.request("ssap://x")
    assert "reduced" not in str(info.value)


def test_set_backlight_validates_range(stub_tv):
    with pytest.raises(ValueError):
        stub_tv.set_backlight(150)


def test_get_settings_unwraps_settings_key(stub_tv):
    stub_tv._client.responses["ssap://settings/getSystemSettings"] = {
        "returnValue": True,
        "settings": {"backlight": 80},
    }
    assert stub_tv.get_settings("picture", ["backlight"]) == {"backlight": 80}


# -- channels / inputs / apps ----------------------------------------------


def test_set_channel_picks_number_vs_id_key(stub_tv):
    stub_tv.set_channel("5")
    stub_tv.set_channel("uk-bbc-one-hd")
    assert ("ssap://tv/openChannel", {"channelNumber": "5"}) in stub_tv._client.calls
    assert (
        "ssap://tv/openChannel",
        {"channelId": "uk-bbc-one-hd"},
    ) in stub_tv._client.calls


def test_launch_app_includes_params_only_when_given(stub_tv):
    stub_tv.launch_app("netflix")
    stub_tv.launch_app("youtube.leanback.v4", {"contentTarget": "abc"})
    assert ("ssap://system.launcher/launch", {"id": "netflix"}) in stub_tv._client.calls
    assert (
        "ssap://system.launcher/launch",
        {"id": "youtube.leanback.v4", "params": {"contentTarget": "abc"}},
    ) in stub_tv._client.calls


# -- power ------------------------------------------------------------------


def test_power_on_without_known_mac_raises(tmp_path):
    tv = LGTV("192.0.2.1", config_path=tmp_path / "config.json")
    with pytest.raises(LGTVError, match="No MAC address"):
        tv.power_on()


def test_power_on_uses_stored_mac(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    config.update_tv("192.0.2.1", cfg, client_key="k", mac="aa:bb:cc:dd:ee:ff")
    sent = []
    monkeypatch.setattr("lgtvpy.tv.send_magic_packet", lambda mac: sent.append(mac))
    LGTV("192.0.2.1", config_path=cfg).power_on()
    assert sent == ["aa:bb:cc:dd:ee:ff"]


def test_power_on_wakes_every_stored_mac(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    config.update_tv("192.0.2.1", cfg, mac=["aa:aa:aa:aa:aa:aa", "bb:bb:bb:bb:bb:bb"])
    sent = []
    monkeypatch.setattr("lgtvpy.tv.send_magic_packet", lambda mac: sent.append(mac))
    LGTV("192.0.2.1", config_path=cfg).power_on()
    assert sent == ["aa:aa:aa:aa:aa:aa", "bb:bb:bb:bb:bb:bb"]


def test_mac_falls_back_to_connection_info_when_sw_info_refused(stub_tv, tmp_path):
    # webOS 26 unsigned pairing: getCurrentSWInformation is a 401.
    stub = stub_tv._client
    stub.responses["ssap://com.webos.service.update/getCurrentSWInformation"] = (
        RequestError("401 insufficient permissions")
    )
    stub.responses["ssap://com.webos.service.connectionmanager/getinfo"] = {
        "returnValue": True,
        "wiredInfo": {"macAddress": "11:22:33:44:55:66"},
        "wifiInfo": {"macAddress": "aa:bb:cc:dd:ee:ff"},
    }
    stub_tv._remember_mac()
    stored = config.get_tv("192.0.2.1", tmp_path / "config.json")["mac"]
    assert stored == ["11:22:33:44:55:66", "aa:bb:cc:dd:ee:ff"]


def test_mac_fallback_ignores_empty_interfaces(stub_tv, tmp_path):
    stub = stub_tv._client
    stub.responses["ssap://com.webos.service.update/getCurrentSWInformation"] = {}
    stub.responses["ssap://com.webos.service.connectionmanager/getinfo"] = {
        "wiredInfo": {"macAddress": "00:00:00:00:00:00"},
        "wifiInfo": {"macAddress": "aa:bb:cc:dd:ee:ff"},
    }
    stub_tv._remember_mac()
    assert config.get_tv("192.0.2.1", tmp_path / "config.json")["mac"] == (
        "aa:bb:cc:dd:ee:ff"
    )


def test_connect_on_webos26_pairs_unsigned_and_finds_mac(fake_tv, tmp_path):
    cfg = tmp_path / "config.json"
    fake_tv.reject_signed = True
    fake_tv.routes["ssap://com.webos.service.update/getCurrentSWInformation"] = {
        "returnValue": False,
        "errorText": "401 insufficient permissions",
    }
    fake_tv.routes["ssap://com.webos.service.connectionmanager/getinfo"] = {
        "returnValue": True,
        "wifiInfo": {"macAddress": "aa:bb:cc:dd:ee:ff"},
    }
    tv = LGTV("10.0.0.9", config_path=cfg)
    tv.connect()
    assert tv.signed_pairing is False
    tv.close()
    stored = config.get_tv("10.0.0.9", cfg)
    assert stored == {"client_key": "test-client-key", "mac": "aa:bb:cc:dd:ee:ff"}


def test_screen_off_uses_tvpower_service(stub_tv):
    stub_tv.screen_off()
    assert (
        "ssap://com.webos.service.tvpower/power/turnOffScreen",
        {"standbyMode": "active"},
    ) in stub_tv._client.calls


# -- info / status ----------------------------------------------------------


def test_system_info_uses_pre_registration_copy_when_blocked(stub_tv):
    stub = stub_tv._client
    stub.system_info = {"modelName": "OLED42C34LA", "returnValue": True}
    stub.responses["ssap://system/getSystemInfo"] = RequestError("401")
    assert stub_tv.system_info()["modelName"] == "OLED42C34LA"
    assert "ssap://com.webos.service.update/getCurrentSWInformation" not in stub.uris()


def test_system_info_falls_back_when_blocked(stub_tv):
    stub = stub_tv._client
    stub.responses["ssap://system/getSystemInfo"] = RequestError("401")
    stub.responses["ssap://com.webos.service.update/getCurrentSWInformation"] = {
        "returnValue": True,
        "product_name": "webOSTV 23",
    }
    assert stub_tv.system_info()["product_name"] == "webOSTV 23"


def test_status_survives_partial_failures(stub_tv):
    stub = stub_tv._client
    stub.responses["ssap://audio/getVolume"] = {"volumeStatus": {"volume": 3}}
    stub.responses["ssap://com.webos.service.tvpower/power/getPowerState"] = (
        RequestError("401")
    )
    status = stub_tv.status()
    assert status["volume"] == 3
    assert "unavailable" in status["power"]


# -- buttons ----------------------------------------------------------------


def test_button_opens_pointer_socket_and_uppercases(fake_tv, tmp_path):
    tv = LGTV("192.0.2.1", config_path=tmp_path / "config.json")
    tv._client = StubClient({
        "ssap://com.webos.service.networkinput/getPointerInputSocket": {
            "returnValue": True,
            "socketPath": "wss://192.0.2.1:3001/resources/x/netinput.pointer",
        }
    })
    tv.button("home", repeat=2)
    pointer_ws = fake_tv.sockets[-1]
    assert pointer_ws.sent == ["type:button\nname:HOME\n\n"] * 2


def test_button_without_socket_path_raises(stub_tv):
    stub_tv._client.responses[
        "ssap://com.webos.service.networkinput/getPointerInputSocket"
    ] = {"returnValue": True}
    with pytest.raises(LGTVError, match="pointer input socket"):
        stub_tv.button("HOME")
