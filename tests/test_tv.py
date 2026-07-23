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


def test_screen_off_uses_tvpower_service(stub_tv):
    stub_tv.screen_off()
    assert (
        "ssap://com.webos.service.tvpower/power/turnOffScreen",
        {"standbyMode": "active"},
    ) in stub_tv._client.calls


# -- info / status ----------------------------------------------------------


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
