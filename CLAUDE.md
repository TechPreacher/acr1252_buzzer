# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A single-file Python CLI (`acr1252_buzzer.py`) that reads and writes the buzzer bits of the
"LED and Buzzer Status Indicator Behavior" byte stored in the non-volatile memory of an
ACS ACR1252U NFC reader. It talks to the reader through PC/SC escape commands via `pyscard`.
There is no build step and no package; tests live in `tests/` (pytest).

## Commands

```sh
uv run acr1252_buzzer.py --list              # PEP 723 header pulls in pyscard; no venv needed
uv run acr1252_buzzer.py                     # show current behaviour byte, writes nothing
uv run acr1252_buzzer.py --silent --dry-run  # compute new byte, do not write
uv run --with pytest python -m pytest        # full test suite, no hardware or pyscard needed
uv run --with pytest python -m pytest tests/test_cli.py -k dry_run   # single test
```

Without uv: `pip install -r requirements.txt pytest`, then `python3 acr1252_buzzer.py` /
`python -m pytest`.

Anything that is not `--list`, `--dry-run` or the tests requires a physical ACR1252U attached.

## Tests

`tests/conftest.py` installs a stub `smartcard.scard` module in `sys.modules` *before*
importing the script, so pyscard is never loaded. Because the script does
`from smartcard.scard import SCardControl, ...`, tests patch the names on the
`acr1252_buzzer` module (`monkeypatch.setattr(mod, "SCardControl", ...)`), not on `smartcard`.

`FakeReader` in conftest simulates a reader: holds the behaviour byte, answers read/write
escape commands with the `E1 00 00 00 01 <byte>` frame, records connect modes and control
codes, and can be told to lie on read-back (`lie_on_readback=`) to exercise the exit-code-2
path. `run_main(*argv)` runs `main()` and returns `(exit_code, stdout, stderr)`.

## How it works

Flow in `main()`: establish PC/SC context -> list readers -> `pick_reader` (prefers the `PICC`
interface, avoids the `SAM` slot) -> `connect` (tries `SCARD_SHARE_DIRECT` first so no tag is
needed) -> `escape` read -> `apply_args` computes the new byte -> optional write + read-back
verification (exit code 2 on mismatch).

Protocol constants come from the ACR1252U API manual v1.17 sections 5.4.5 / 5.4.6:

- read `E0 00 00 21 00`, write `E0 00 00 21 01 <byte>`, both answer `E1 00 00 00 01 <byte>`
- bit 3 insert beep, bit 4 remove beep (only effective with bit 3), bit 5 power-on beep
- bits 0-2, 6, 7 are LED behaviour and must never be modified; `BUZZER_MASK` guards this

The escape control code is `SCARD_CTL_CODE(3500)` for ACS/Windows drivers; generic libccid on
Linux uses function 1 (`--ctl 1`) and needs escape commands enabled in the driver. On macOS
Apple's built-in CCID driver blocks escapes entirely; `docs/macos-driver.md` has the fix (acsccid).

## Conventions

- Keep it a single file with no dependencies beyond `pyscard`; the PEP 723 header at the top
  is the dependency declaration for `uv run`, keep it in sync with `requirements.txt`.
- Every error path goes through `die()` so messages land on stderr with a non-zero exit.
- Writes are always verified by reading back; keep that invariant if the write path changes.
