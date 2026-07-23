"""Config store tests."""

from lgtvpy import config


def test_load_missing_file_returns_empty(tmp_path):
    assert config.load(tmp_path / "nope.json") == {}


def test_load_corrupt_file_returns_empty(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")
    assert config.load(path) == {}


def test_update_and_get_tv_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    config.update_tv("10.0.0.5", path, client_key="abc")
    config.update_tv("10.0.0.5", path, mac="aa:bb:cc:dd:ee:ff")
    entry = config.get_tv("10.0.0.5", path)
    assert entry == {"client_key": "abc", "mac": "aa:bb:cc:dd:ee:ff"}


def test_update_tv_ignores_none_values(tmp_path):
    path = tmp_path / "config.json"
    config.update_tv("10.0.0.5", path, client_key="abc", mac=None)
    assert config.get_tv("10.0.0.5", path) == {"client_key": "abc"}


def test_get_default_ip(tmp_path):
    path = tmp_path / "config.json"
    assert config.get_default_ip(path) is None            # nothing paired
    config.update_tv("10.0.0.5", path, client_key="a")
    assert config.get_default_ip(path) == "10.0.0.5"      # single TV
    config.update_tv("10.0.0.6", path, client_key="b")
    assert config.get_default_ip(path) is None            # ambiguous


def test_save_creates_parent_directories(tmp_path):
    path = tmp_path / "deep" / "nested" / "config.json"
    config.save({"x": {}}, path)
    assert config.load(path) == {"x": {}}
