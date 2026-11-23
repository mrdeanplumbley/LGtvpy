"""TOML profile: load/validate/plan/apply/capture/dumps."""

import pytest

from lgtvpy import profiles
from lgtvpy.client import LGTVError
from tests.conftest import StubClient


FILM = """
name = "Film"
input = "HDMI_1"
volume = 14

[picture]
pictureMode = "filmMaker"
backlight = 60
contrast = 85

[sound]
soundMode = "movie"
"""


def write(tmp_path, text, name="p.toml"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# -- load / validate --------------------------------------------------------


def test_load_valid_profile(tmp_path):
    profile = profiles.load(write(tmp_path, FILM))
    assert profile["name"] == "Film"
    assert profile["picture"]["backlight"] == 60


def test_load_missing_file_raises():
    with pytest.raises(LGTVError, match="not found"):
        profiles.load("does-not-exist.toml")


def test_load_invalid_toml_raises(tmp_path):
    with pytest.raises(LGTVError, match="Invalid TOML"):
        profiles.load(write(tmp_path, "this is = = not toml"))


def test_unknown_top_level_key_rejected():
    with pytest.raises(LGTVError, match="Unknown profile key"):
        profiles.validate({"volme": 10})  # typo for "volume"


def test_nested_setting_rejected():
    with pytest.raises(LGTVError, match="scalar"):
        profiles.validate({"picture": {"bad": {"nested": 1}}})


def test_empty_profile_rejected():
    with pytest.raises(LGTVError, match="does nothing"):
        profiles.validate({"name": "just a label"})


# -- plan -------------------------------------------------------------------


def test_plan_orders_actions(tmp_path):
    profile = profiles.load(write(tmp_path, FILM))
    assert profiles.plan(profile) == [
        "switch input -> HDMI_1",
        "set picture: pictureMode=filmMaker, backlight=60, contrast=85",
        "set sound: soundMode=movie",
        "set volume -> 14",
    ]


# -- apply ------------------------------------------------------------------


def test_apply_dry_run_touches_nothing(stub_tv):
    profile = {"volume": 10, "picture": {"backlight": 30}}
    steps = profiles.apply(stub_tv, profile, dry_run=True)
    assert steps  # plan returned
    assert stub_tv._client.calls == []  # nothing sent


def test_apply_sets_input_first_then_categories_then_volume(stub_tv):
    profile = {
        "input": "HDMI_1",
        "volume": 14,
        "picture": {"backlight": 60},
        "sound": {"soundMode": "movie"},
    }
    profiles.apply(stub_tv, profile, settle=0)
    uris = stub_tv._client.uris()
    assert uris[0] == "ssap://tv/switchInput"
    # both settings categories go through the alert bridge
    assert uris.count("ssap://system.notifications/createAlert") == 2
    assert "ssap://audio/setVolume" in uris
    assert uris.index("ssap://tv/switchInput") < uris.index("ssap://audio/setVolume")


def test_apply_picture_mode_applied_before_other_keys(stub_tv):
    # Two-phase: pictureMode in its own settings call first, then the rest.
    stub = stub_tv._client
    stub.responses["ssap://system.notifications/createAlert"] = {
        "returnValue": True,
        "alertId": "a",
    }
    profile = {"picture": {"pictureMode": "game", "backlight": 100, "contrast": 90}}
    profiles.apply(stub_tv, profile, settle=0)

    # Grab the params sent to each setSystemSettings via the alert button.
    settings_calls = [
        payload["buttons"][0]["params"]["settings"]
        for uri, payload in stub.calls
        if uri == "ssap://system.notifications/createAlert"
    ]
    assert settings_calls[0] == {"pictureMode": "game"}          # mode first, alone
    assert settings_calls[1] == {"backlight": 100, "contrast": 90}  # then the rest


def test_apply_game_genre_applied_before_game_values(stub_tv):
    # Switching genre reloads that genre's stored game* values, so it goes first.
    stub = stub_tv._client
    stub.responses["ssap://system.notifications/createAlert"] = {
        "returnValue": True,
        "alertId": "a",
    }
    profile = {"other": {"gameSharpness": 0, "gameGenre": "Standard", "gameColorDepth": 55}}
    profiles.apply(stub_tv, profile, settle=0)
    settings_calls = [
        payload["buttons"][0]["params"]["settings"]
        for uri, payload in stub.calls
        if uri == "ssap://system.notifications/createAlert"
    ]
    assert settings_calls[0] == {"gameGenre": "Standard"}
    assert settings_calls[1] == {"gameSharpness": 0, "gameColorDepth": 55}


def test_apply_single_key_category_is_one_call(stub_tv):
    stub = stub_tv._client
    stub.responses["ssap://system.notifications/createAlert"] = {
        "returnValue": True,
        "alertId": "a",
    }
    profiles.apply(stub_tv, {"sound": {"soundMode": "movie"}}, settle=0)
    creates = [u for u, _ in stub.calls if u == "ssap://system.notifications/createAlert"]
    assert len(creates) == 1  # not split


def test_apply_mute_and_sound_output(stub_tv):
    profiles.apply(
        stub_tv,
        {"mute": True, "sound_output": "external_arc"},
        settle=0,
    )
    assert ("ssap://audio/setMute", {"mute": True}) in stub_tv._client.calls
    assert (
        "ssap://audio/changeSoundOutput",
        {"output": "external_arc"},
    ) in stub_tv._client.calls


# -- capture ----------------------------------------------------------------


def test_capture_reads_state_into_profile(tmp_path):
    from lgtvpy.tv import LGTV

    tv = LGTV("192.0.2.1", config_path=tmp_path / "config.json")
    tv._client = StubClient({
        "ssap://com.webos.applicationManager/getForegroundAppInfo": {
            "returnValue": True,
            "appId": "com.webos.app.hdmi2",
        },
        "ssap://audio/getVolume": {"volumeStatus": {"volume": 12}},
        "ssap://settings/getSystemSettings": _settings_router,
    })

    profile = tv.capture_profile(name="Snapshot")
    assert profile["name"] == "Snapshot"
    assert profile["input"] == "HDMI_2"
    assert profile["volume"] == 12
    # numeric strings from the TV are coerced to ints
    assert profile["picture"]["contrast"] == 85
    assert profile["picture"]["pictureMode"] == "filmMaker"
    assert profile["sound"] == {"soundMode": "movie"}


def _capture_tv(tmp_path, picture_route):
    from lgtvpy.tv import LGTV

    tv = LGTV("192.0.2.1", config_path=tmp_path / "config.json")
    tv._client = StubClient({
        "ssap://settings/getSystemSettings": lambda payload: (
            picture_route(payload) if payload["category"] == "picture"
            else {"settings": {}}
        ),
    })
    return tv


def test_capture_requests_extended_picture_keys(tmp_path):
    from lgtvpy.tv import PICTURE_KEYS_EXTENDED

    requested = []

    def route(payload):
        requested.append(payload["keys"])
        return {"settings": {
            "pictureMode": "expert2",
            "truMotionMode": "off",
            "hdrDynamicToneMapping": "HGIG",
            "blackLevel": {"ntsc": "low", "pal": "auto"},  # dict -> skipped
        }}

    profile = _capture_tv(tmp_path, route).capture_profile()
    assert requested == [PICTURE_KEYS_EXTENDED]
    assert profile["picture"] == {
        "pictureMode": "expert2",
        "truMotionMode": "off",
        "hdrDynamicToneMapping": "HGIG",
    }
    profiles.validate(profile)  # a captured profile must load back


def test_capture_falls_back_to_basic_keys_on_older_firmware(tmp_path):
    from lgtvpy.client import RequestError
    from lgtvpy.tv import PICTURE_KEYS, PICTURE_KEYS_EXTENDED

    requested = []

    def route(payload):
        requested.append(payload["keys"])
        if payload["keys"] == PICTURE_KEYS_EXTENDED:
            raise RequestError("Some keys are not allowed")
        return {"settings": {"backlight": "40"}}

    profile = _capture_tv(tmp_path, route).capture_profile()
    assert requested == [PICTURE_KEYS_EXTENDED, PICTURE_KEYS]
    assert profile["picture"] == {"backlight": 40}


def _settings_router(payload):
    category = payload["category"]
    if category == "picture":
        return {
            "settings": {
                "contrast": "85",       # TV returns strings for some keys
                "pictureMode": "filmMaker",
                "backlight": 60,
            }
        }
    if category == "sound":
        return {"settings": {"soundMode": "movie"}}
    return {"settings": {}}


# -- dumps ------------------------------------------------------------------


def test_dumps_scalars_before_tables_and_types():
    text = profiles.dumps({
        "name": "X",
        "volume": 14,
        "mute": False,
        "picture": {"backlight": 60, "pictureMode": "game"},
    })
    lines = text.splitlines()
    assert lines[0] == 'name = "X"'
    assert 'volume = 14' in lines
    assert 'mute = false' in lines
    assert "[picture]" in lines
    assert 'pictureMode = "game"' in lines
    # scalars come before the table header
    assert lines.index("volume = 14") < lines.index("[picture]")


def test_dumps_load_roundtrip(tmp_path):
    original = {
        "name": "Round",
        "input": "HDMI_1",
        "volume": 20,
        "picture": {"backlight": 45, "pictureMode": "filmMaker"},
    }
    path = write(tmp_path, profiles.dumps(original), "round.toml")
    assert profiles.load(path) == original


def test_toml_value_escapes_quotes():
    assert profiles._toml_value('say "hi"') == '"say \\"hi\\""'


@pytest.mark.parametrize("value,expected", [("85", 85), ("-3", -3), ("x", "x"), (60, 60)])
def test_coerce(value, expected):
    assert profiles._coerce(value) == expected


@pytest.mark.parametrize(
    "app,expected",
    [
        ("com.webos.app.hdmi2", "HDMI_2"),
        ("com.webos.app.hdmi4", "HDMI_4"),
        ("netflix", None),
        ("", None),
    ],
)
def test_app_to_input(app, expected):
    assert profiles._app_to_input(app) == expected
