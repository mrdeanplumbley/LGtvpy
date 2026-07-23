"""CLI dispatch tests: each command drives the right LGTV method."""

import pytest

import lgtvpy.cli as cli


class FakeLGTV:
    """Recording facade matching the LGTV surface the CLI uses."""

    last = None
    all_calls = []  # aggregated across instances (one per CLI invocation)

    def __init__(self, ip=None, timeout=None, on_pair_prompt=None, **kwargs):
        self.ip = ip or "9.9.9.9"
        self.calls = []
        FakeLGTV.last = self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def _rec(self, name, *args):
        self.calls.append((name, *args))
        FakeLGTV.all_calls.append((name, *args))

    # power
    def power_on(self, mac=None): self._rec("power_on", mac)
    def power_off(self): self._rec("power_off")
    def screen_off(self): self._rec("screen_off")
    def screen_on(self): self._rec("screen_on")
    def status(self): return {"power": "Active"}

    # audio
    volume = 12
    muted = False
    def set_volume(self, level): self._rec("set_volume", level)
    def volume_up(self): self._rec("volume_up")
    def volume_down(self): self._rec("volume_down")
    def set_mute(self, mute): self._rec("set_mute", mute)
    def toggle_mute(self): self._rec("toggle_mute"); return True
    def get_sound_output(self): return "tv_speaker"
    def set_sound_output(self, output): self._rec("set_sound_output", output)

    # apps / inputs / channels
    def list_apps(self): return [{"id": "netflix", "title": "Netflix"}]
    def current_app(self): return "netflix"
    def launch_app(self, app_id, params=None):
        self._rec("launch_app", app_id, params); return {"returnValue": True}
    def close_app(self, app_id): self._rec("close_app", app_id)
    def open_url(self, url): self._rec("open_url", url); return {}
    def list_inputs(self): return [{"id": "HDMI_1", "label": "PC", "connected": True}]
    def set_input(self, input_id): self._rec("set_input", input_id)
    def channel_up(self): self._rec("channel_up")
    def channel_down(self): self._rec("channel_down")
    def set_channel(self, channel): self._rec("set_channel", channel)
    def list_channels(self): return [{"channelNumber": "5", "channelName": "BBC One"}]

    # media / buttons / text / notify
    def play(self): self._rec("play")
    def pause(self): self._rec("pause")
    def stop(self): self._rec("stop")
    def rewind(self): self._rec("rewind")
    def fast_forward(self): self._rec("fast_forward")
    def button(self, name, repeat=1): self._rec("button", name, repeat)
    def type_text(self, text): self._rec("type_text", text)
    def send_enter(self): self._rec("send_enter")
    def delete_chars(self, count): self._rec("delete_chars", count)
    def notify(self, message): self._rec("notify", message)

    # settings / info / raw
    def get_settings(self, category, keys=None): return {"backlight": 50}
    def set_settings(self, category, settings): self._rec("set_settings", category, settings)
    def set_picture_mode(self, mode): self._rec("set_picture_mode", mode)
    def set_sound_mode(self, mode): self._rec("set_sound_mode", mode)
    def set_backlight(self, level): self._rec("set_backlight", level)
    def set_energy_saving(self, level): self._rec("set_energy_saving", level)
    def system_info(self): return {"modelName": "TEST"}
    def software_info(self): return {"device_id": "aa:bb"}
    def request(self, uri, payload=None):
        self._rec("request", uri, payload); return {"echo": True}


@pytest.fixture
def fake_cli(monkeypatch):
    monkeypatch.setattr(cli, "LGTV", FakeLGTV)
    FakeLGTV.last = None
    FakeLGTV.all_calls = []
    return FakeLGTV


def run_cli(argv):
    return cli.run(cli.build_parser().parse_args(argv))


def calls():
    return FakeLGTV.all_calls


# -- parsing helpers --------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [("85", 85), ("off", "off"), ("true", True), ('{"a": 1}', {"a": 1}), ("-3", -3)],
)
def test_parse_value(raw, expected):
    assert cli._parse_value(raw) == expected


# -- command dispatch -------------------------------------------------------


def test_on_reports_resolved_ip(fake_cli):
    result = run_cli(["on", "--mac", "aa:bb:cc:dd:ee:ff"])
    assert ("power_on", "aa:bb:cc:dd:ee:ff") in calls()
    assert "9.9.9.9" in result  # resolved TV ip, not the unset --ip


def test_off(fake_cli):
    run_cli(["off"])
    assert ("power_off",) in calls()


def test_ip_flag_is_passed_through(fake_cli):
    run_cli(["--ip", "10.1.1.1", "status"])
    assert FakeLGTV.last.ip == "10.1.1.1"


def test_ip_flag_works_after_subcommand(fake_cli):
    # Regression: the README documents `lgtv pair --ip <tv-ip>`.
    run_cli(["status", "--ip", "10.2.2.2"])
    assert FakeLGTV.last.ip == "10.2.2.2"
    run_cli(["settings", "get", "picture", "--ip", "10.3.3.3"])
    assert FakeLGTV.last.ip == "10.3.3.3"
    run_cli(["--ip", "10.4.4.4", "vol", "--timeout", "3"])
    assert FakeLGTV.last.ip == "10.4.4.4"  # root value survives subparser


def test_vol_show_set_and_step(fake_cli):
    assert run_cli(["vol"]) == {"volume": 12, "muted": False}
    run_cli(["vol", "25"])
    assert ("set_volume", 25) in calls()
    run_cli(["vol", "up"])
    assert ("volume_up",) in calls()


def test_mute_toggle_and_explicit(fake_cli):
    assert run_cli(["mute"]) == {"muted": True}
    assert ("toggle_mute",) in calls()
    run_cli(["mute", "off"])
    assert ("set_mute", False) in calls()


def test_launch_with_json_params(fake_cli):
    run_cli(["launch", "youtube.leanback.v4", "--params", '{"contentTarget": "xyz"}'])
    assert ("launch_app", "youtube.leanback.v4", {"contentTarget": "xyz"}) in calls()


def test_input_switch(fake_cli):
    run_cli(["input", "HDMI_2"])
    assert ("set_input", "HDMI_2") in calls()


def test_channel_variants(fake_cli):
    run_cli(["channel", "up"])
    run_cli(["channel", "7"])
    assert ("channel_up",) in calls()
    assert ("set_channel", "7") in calls()


def test_media_ff_maps_to_fast_forward(fake_cli):
    run_cli(["media", "ff"])
    assert ("fast_forward",) in calls()


def test_button_sequence_with_repeat(fake_cli):
    run_cli(["button", "UP", "ENTER", "--repeat", "2"])
    assert ("button", "UP", 2) in calls()
    assert ("button", "ENTER", 2) in calls()


def test_buttons_lists_names(fake_cli):
    assert "HOME" in run_cli(["buttons"])


def test_settings_set_parses_value_types(fake_cli):
    run_cli(["settings", "set", "picture", "backlight", "40"])
    assert ("set_settings", "picture", {"backlight": 40}) in calls()
    run_cli(["settings", "set", "sound", "soundMode", "movie"])
    assert ("set_settings", "sound", {"soundMode": "movie"}) in calls()


def test_settings_get(fake_cli):
    assert run_cli(["settings", "get", "picture"]) == {"backlight": 50}


def test_shortcut_settings_commands(fake_cli):
    run_cli(["picture-mode", "filmMaker"])
    run_cli(["sound-mode", "movie"])
    run_cli(["backlight", "35"])
    run_cli(["energy-saving", "off"])
    assert ("set_picture_mode", "filmMaker") in calls()
    assert ("set_sound_mode", "movie") in calls()
    assert ("set_backlight", 35) in calls()
    assert ("set_energy_saving", "off") in calls()


def test_notify_and_text(fake_cli):
    run_cli(["notify", "hello"])
    assert ("notify", "hello") in calls()
    run_cli(["text", "stranger things"])
    assert ("type_text", "stranger things") in calls()
    run_cli(["delete", "5"])
    assert ("delete_chars", 5) in calls()


def test_raw_with_payload(fake_cli):
    result = run_cli(["raw", "ssap://audio/getVolume", '{"x": 1}'])
    assert ("request", "ssap://audio/getVolume", {"x": 1}) in calls()
    assert result == {"echo": True}


def test_apps_output_is_trimmed(fake_cli):
    assert run_cli(["apps"]) == [{"id": "netflix", "title": "Netflix"}]


def test_main_returns_error_code_on_lgtv_error(fake_cli, monkeypatch, capsys):
    from lgtvpy.client import LGTVError

    def boom(self):
        raise LGTVError("nope")

    monkeypatch.setattr(FakeLGTV, "status", boom)
    assert cli.main(["status"]) == 1
    assert "nope" in capsys.readouterr().err
