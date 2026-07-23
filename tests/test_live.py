"""Optional read-only checks against a real, already-paired TV.

Skipped unless LGTV_LIVE=1 is set (the TV must be on):

    LGTV_LIVE=1 pytest -m live          # bash
    $env:LGTV_LIVE="1"; pytest -m live  # PowerShell

These only READ state - nothing on the TV is changed.
"""

import os

import pytest

from lgtvpy import LGTV

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        not os.environ.get("LGTV_LIVE"),
        reason="set LGTV_LIVE=1 to run against your paired TV",
    ),
]


@pytest.fixture(scope="module")
def tv():
    tv = LGTV()
    tv.connect()
    yield tv
    tv.close()


def test_status(tv):
    status = tv.status()
    assert status["power"]
    assert isinstance(status["volume"], int)


def test_volume_and_mute_read(tv):
    assert 0 <= tv.volume <= 100
    assert isinstance(tv.muted, bool)


def test_picture_settings_read(tv):
    settings = tv.get_picture_settings()
    assert settings, "expected at least one picture setting back"


def test_inputs_listed(tv):
    inputs = tv.list_inputs()
    assert any(device.get("id", "").startswith("HDMI") for device in inputs)


def test_apps_listed(tv):
    assert len(tv.list_apps()) > 10


def test_software_info_has_mac(tv):
    assert tv.software_info().get("device_id", "").count(":") == 5
