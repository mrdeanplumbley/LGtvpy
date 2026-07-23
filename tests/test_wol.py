"""Wake-on-LAN magic packet tests."""

import pytest

from lgtvpy import wol


class FakeSocket:
    sent = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def setsockopt(self, *args):
        pass

    def sendto(self, data, addr):
        FakeSocket.sent.append((data, addr))


@pytest.fixture
def fake_socket(monkeypatch):
    FakeSocket.sent = []
    monkeypatch.setattr(wol.socket, "socket", FakeSocket)
    return FakeSocket


def test_magic_packet_format(fake_socket):
    wol.send_magic_packet("aa:bb:cc:dd:ee:ff")
    mac_bytes = bytes.fromhex("aabbccddeeff")
    for data, _addr in fake_socket.sent:
        assert len(data) == 102          # 6 x 0xFF + 16 x 6-byte MAC
        assert data[:6] == b"\xff" * 6
        assert data[6:] == mac_bytes * 16


def test_sends_to_both_wol_ports(fake_socket):
    wol.send_magic_packet("aa:bb:cc:dd:ee:ff", broadcast="192.168.1.255")
    assert [addr for _d, addr in fake_socket.sent] == [
        ("192.168.1.255", 9),
        ("192.168.1.255", 7),
    ]


@pytest.mark.parametrize("mac", ["AA-BB-CC-DD-EE-FF", "aabbccddeeff"])
def test_accepts_dash_and_bare_formats(fake_socket, mac):
    wol.send_magic_packet(mac)
    assert fake_socket.sent


@pytest.mark.parametrize("mac", ["", "aa:bb:cc", "zz:bb:cc:dd:ee:ff", "aa:bb:cc:dd:ee:ff:00"])
def test_invalid_mac_raises(fake_socket, mac):
    with pytest.raises(ValueError):
        wol.send_magic_packet(mac)
    assert fake_socket.sent == []
