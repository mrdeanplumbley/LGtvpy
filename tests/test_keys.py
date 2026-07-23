"""Sanity checks on the exported button list."""

from lgtvpy import BUTTONS


def test_buttons_are_unique_uppercase_strings():
    assert BUTTONS
    assert len(BUTTONS) == len(set(BUTTONS))
    for name in BUTTONS:
        assert isinstance(name, str)
        assert name == name.upper()


def test_core_buttons_present():
    for name in ("HOME", "BACK", "UP", "DOWN", "LEFT", "RIGHT", "ENTER", "MUTE"):
        assert name in BUTTONS
