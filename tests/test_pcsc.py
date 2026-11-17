"""connect() and escape(): the thin PC/SC wrappers, with the stub patched per test."""

import pytest

from conftest import SCARD_E_NO_SMARTCARD, SCARD_S_SUCCESS


def test_connect_uses_direct_mode_first(mod, monkeypatch):
    calls = []

    def fake_connect(ctx, reader, mode, proto):
        calls.append((mode, proto))
        return SCARD_S_SUCCESS, "CARD", proto

    monkeypatch.setattr(mod, "SCardConnect", fake_connect)
    assert mod.connect("CTX", "R") == "CARD"
    assert calls == [(mod.SCARD_SHARE_DIRECT, 0)]


def test_connect_falls_back_to_shared_mode(mod, monkeypatch):
    calls = []

    def fake_connect(ctx, reader, mode, proto):
        calls.append((mode, proto))
        if mode == mod.SCARD_SHARE_DIRECT:
            return SCARD_E_NO_SMARTCARD, None, 0
        return SCARD_S_SUCCESS, "CARD", proto

    monkeypatch.setattr(mod, "SCardConnect", fake_connect)
    assert mod.connect("CTX", "R") == "CARD"
    assert [m for m, _ in calls] == [
        mod.SCARD_SHARE_DIRECT,
        mod.SCARD_SHARE_DIRECT,
        mod.SCARD_SHARE_SHARED,
    ]
    assert calls[-1][1] == mod.SCARD_PROTOCOL_T0 | mod.SCARD_PROTOCOL_T1


def test_connect_dies_when_every_mode_fails(mod, monkeypatch, capsys):
    monkeypatch.setattr(mod, "SCardConnect", lambda *a: (SCARD_E_NO_SMARTCARD, None, 0))
    with pytest.raises(SystemExit) as e:
        mod.connect("CTX", "My Reader")
    assert e.value.code == 1
    err = capsys.readouterr().err
    assert "could not connect to 'My Reader'" in err
    assert "tag lying on the reader" in err


def test_escape_returns_payload_byte(mod, monkeypatch):
    monkeypatch.setattr(mod, "SCardControl", lambda h, c, cmd: (SCARD_S_SUCCESS, (0xE1, 0, 0, 0, 1, 0x5A)))
    assert mod.escape("CARD", 1, mod.CMD_READ, verbose=False) == 0x5A


def test_escape_sends_the_exact_command_and_ctl_code(mod, monkeypatch):
    seen = {}

    def fake_control(hcard, ctl, cmd):
        seen.update(hcard=hcard, ctl=ctl, cmd=list(cmd))
        return SCARD_S_SUCCESS, [0xE1, 0, 0, 0, 1, 0x47]

    monkeypatch.setattr(mod, "SCardControl", fake_control)
    mod.escape("CARD", 0x42000DAC, mod.CMD_WRITE + [0x47], verbose=False)
    assert seen == dict(hcard="CARD", ctl=0x42000DAC, cmd=[0xE0, 0x00, 0x00, 0x21, 0x01, 0x47])


@pytest.mark.parametrize(
    "resp",
    [
        [],                                   # empty
        [0xE1, 0, 0, 0, 1],                   # too short
        [0xE1, 0, 0, 0, 1, 0x47, 0x00],       # too long
        [0xE1, 0, 0, 0, 2, 0x47],             # wrong length field
        [0x90, 0x00],                         # APDU status word instead of escape response
    ],
)
def test_escape_rejects_malformed_response(mod, monkeypatch, capsys, resp):
    monkeypatch.setattr(mod, "SCardControl", lambda h, c, cmd: (SCARD_S_SUCCESS, resp))
    with pytest.raises(SystemExit) as e:
        mod.escape("CARD", 1, mod.CMD_READ, verbose=False)
    assert e.value.code == 1
    assert "unexpected response" in capsys.readouterr().err


def test_escape_failure_prints_driver_hints(mod, monkeypatch, capsys):
    monkeypatch.setattr(mod, "SCardControl", lambda h, c, cmd: (0x80100016, []))
    with pytest.raises(SystemExit):
        mod.escape("CARD", 1, mod.CMD_READ, verbose=False)
    err = capsys.readouterr().err
    assert "escape command failed" in err
    assert "EscapeCommandEnable" in err
    assert "--ctl 1" in err


def test_escape_verbose_dumps_bytes(mod, monkeypatch, capsys):
    monkeypatch.setattr(mod, "SCardControl", lambda h, c, cmd: (SCARD_S_SUCCESS, [0xE1, 0, 0, 0, 1, 0x7F]))
    mod.escape("CARD", 1, mod.CMD_READ, verbose=True)
    out = capsys.readouterr().out
    assert "> E0 00 00 21 00" in out
    assert "< E1 00 00 00 01 7F" in out
