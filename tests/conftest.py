"""
Test fixtures.

The script imports ``smartcard.scard`` (pyscard) at module level. pyscard needs a
native PC/SC stack, so the tests install a stub module *before* importing the
script. Every test therefore runs without pyscard and without a reader attached.
"""

import argparse
import importlib
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# --- stub smartcard.scard -----------------------------------------------------

SCARD_S_SUCCESS = 0
SCARD_E_NO_SMARTCARD = 0x8010000C
SCARD_E_SHARING_VIOLATION = 0x8010000B
SCARD_E_NOT_TRANSACTED = 0x80100016


def _make_stub():
    scard = types.ModuleType("smartcard.scard")
    scard.SCARD_S_SUCCESS = SCARD_S_SUCCESS
    scard.SCARD_SCOPE_USER = 0
    scard.SCARD_SHARE_DIRECT = 3
    scard.SCARD_SHARE_SHARED = 2
    scard.SCARD_PROTOCOL_T0 = 1
    scard.SCARD_PROTOCOL_T1 = 2
    scard.SCARD_LEAVE_CARD = 0
    scard.SCARD_CTL_CODE = lambda n: 0x42000000 + n
    scard.SCardGetErrorMessage = lambda h: f"stub error 0x{h & 0xFFFFFFFF:08X}"

    def _unconfigured(*_a, **_k):  # pragma: no cover - guards against missing patches
        raise AssertionError("PC/SC call not patched in this test")

    for name in (
        "SCardEstablishContext",
        "SCardReleaseContext",
        "SCardListReaders",
        "SCardConnect",
        "SCardDisconnect",
        "SCardControl",
    ):
        setattr(scard, name, _unconfigured)

    pkg = types.ModuleType("smartcard")
    pkg.scard = scard
    return pkg, scard


_pkg, _scard = _make_stub()
sys.modules.setdefault("smartcard", _pkg)
sys.modules.setdefault("smartcard.scard", _scard)

sys.path.insert(0, str(REPO_ROOT))
buzzer = importlib.import_module("acr1252_buzzer")


# --- fixtures -----------------------------------------------------------------


@pytest.fixture
def mod():
    """The script module, with the PC/SC stub already in place."""
    return buzzer


def make_args(**overrides):
    """Build an argparse namespace equivalent to an invocation with no change flags."""
    base = dict(insert=None, remove=None, poweron=None, silent=False, default=False)
    base.update(overrides)
    return argparse.Namespace(**base)


class FakeReader:
    """
    Simulates the PC/SC layer for one ACR1252U.

    Keeps the behaviour byte in ``value``; records every escape command in
    ``commands``; tracks connect/disconnect/release calls so tests can assert
    the handles are always cleaned up.
    """

    RESP_HEADER = [0xE1, 0x00, 0x00, 0x00, 0x01]

    def __init__(self, names, value=0x7F, direct_ok=True, lie_on_readback=None):
        self.names = list(names)
        self.value = value
        self.direct_ok = direct_ok
        self.lie_on_readback = lie_on_readback
        self.commands = []
        self.connect_modes = []
        self.connected = 0
        self.disconnected = 0
        self.released = 0
        self.ctl_codes = set()

    # PC/SC entry points -------------------------------------------------------

    def SCardEstablishContext(self, scope):
        return SCARD_S_SUCCESS, "CTX"

    def SCardReleaseContext(self, ctx):
        assert ctx == "CTX"
        self.released += 1
        return SCARD_S_SUCCESS

    def SCardListReaders(self, ctx, groups):
        return SCARD_S_SUCCESS, list(self.names)

    def SCardConnect(self, ctx, reader, mode, proto):
        self.connect_modes.append((mode, proto))
        if mode == buzzer.SCARD_SHARE_DIRECT and not self.direct_ok:
            return SCARD_E_NOT_TRANSACTED, None, 0
        self.connected += 1
        return SCARD_S_SUCCESS, "CARD", proto

    def SCardDisconnect(self, hcard, disposition):
        assert hcard == "CARD"
        self.disconnected += 1
        return SCARD_S_SUCCESS

    def SCardControl(self, hcard, ctl, cmd):
        assert hcard == "CARD"
        self.ctl_codes.add(ctl)
        cmd = list(cmd)
        self.commands.append(cmd)
        if cmd == buzzer.CMD_READ:
            v = self.value if self.lie_on_readback is None else self.lie_on_readback
            return SCARD_S_SUCCESS, self.RESP_HEADER + [v]
        if cmd[:5] == buzzer.CMD_WRITE and len(cmd) == 6:
            self.value = cmd[5]
            return SCARD_S_SUCCESS, self.RESP_HEADER + [cmd[5]]
        return SCARD_E_NOT_TRANSACTED, []

    @property
    def writes(self):
        return [c[5] for c in self.commands if c[:5] == buzzer.CMD_WRITE]

    def install(self, monkeypatch):
        for name in (
            "SCardEstablishContext",
            "SCardReleaseContext",
            "SCardListReaders",
            "SCardConnect",
            "SCardDisconnect",
            "SCardControl",
        ):
            monkeypatch.setattr(buzzer, name, getattr(self, name))
        return self


@pytest.fixture
def fake_reader(monkeypatch):
    """Factory: ``fake_reader(names, value=0x7F, ...)`` installs and returns a FakeReader."""

    def _factory(names=("ACS ACR1252 1S CL Reader PICC 0", "ACS ACR1252 1S CL Reader SAM 0"), **kw):
        return FakeReader(names, **kw).install(monkeypatch)

    return _factory


@pytest.fixture
def run_main(monkeypatch, capsys):
    """Run ``main()`` with the given argv; return (exit_code, stdout, stderr)."""

    def _run(*argv):
        monkeypatch.setattr(sys, "argv", ["acr1252_buzzer.py", *argv])
        code = 0
        try:
            buzzer.main()
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 1
        out = capsys.readouterr()
        return code, out.out, out.err

    return _run
