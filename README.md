# acr1252_buzzer

Read or change the buzzer behaviour of an **ACS ACR1252U** NFC reader from the command line.

The reader stores one "LED and Buzzer Status Indicator Behavior" byte in non-volatile memory.
This script lets you flip the three buzzer bits without touching the LED bits, so you can make
the reader stop beeping on every card tap (or turn the beeps back on).

| Bit | Mask   | Meaning                                              |
|-----|--------|------------------------------------------------------|
| 3   | `0x08` | beep on card insertion                               |
| 4   | `0x10` | beep on card removal (only effective if bit 3 is set) |
| 5   | `0x20` | beep at reader power-on                              |

Factory default is `0x7F` (everything on). Bits 0-2, 6 and 7 control the LEDs and are never
modified by this script.

Reference: ACR1252U API manual v1.17, sections 5.4.5 / 5.4.6.

## Requirements

- Python 3.8+
- [pyscard](https://pypi.org/project/pyscard/)
- A working PC/SC stack
  - macOS: built in
  - Linux: `pcscd` + `libccid` (e.g. `apt install pcscd libccid`); building pyscard from
    source additionally needs `swig` and `libpcsclite-dev`
  - Windows: built in (WinSCard)
- An ACR1252U connected via USB. No NFC tag needs to be on the reader.

## Installation

### With uv (recommended, no setup)

The script carries [PEP 723](https://peps.python.org/pep-0723/) inline metadata, so
[uv](https://docs.astral.sh/uv/) resolves and caches `pyscard` on first run. Nothing to
install besides uv itself:

```sh
uv run acr1252_buzzer.py --list
uv run acr1252_buzzer.py --silent
```

Or make it directly executable:

```sh
chmod +x acr1252_buzzer.py
./acr1252_buzzer.py --silent      # uses the python3 on PATH, needs pyscard installed there
```

### With pip

```sh
python3 -m venv .venv
. .venv/bin/activate               # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python3 acr1252_buzzer.py --list
```

## Usage

```sh
python3 acr1252_buzzer.py                   # show current setting (writes nothing)
python3 acr1252_buzzer.py --silent          # turn all three beeps off
python3 acr1252_buzzer.py --default         # turn all three beeps back on
python3 acr1252_buzzer.py --insert off      # only disable the insertion beep
python3 acr1252_buzzer.py --insert on --remove off --poweron off
python3 acr1252_buzzer.py --silent --dry-run   # show what would be written
python3 acr1252_buzzer.py --list            # list PC/SC readers
python3 acr1252_buzzer.py --reader PICC     # pick a reader by name substring
python3 acr1252_buzzer.py -v                # dump raw escape command / response bytes
```

Example:

```
$ python3 acr1252_buzzer.py --silent
reader         : ACS ACR1252 Dual Reader PICC
behaviour byte : 0x7F  (0b01111111)
  bit 3  beep on insertion : on
  bit 4  beep on removal   : on
  bit 5  beep at power-on  : on

after write:
behaviour byte : 0x47  (0b01000111)
  bit 3  beep on insertion : off
  bit 4  beep on removal   : off
  bit 5  beep at power-on  : off
ok (stored in the reader's non-volatile memory)
```

The setting persists in the reader across unplugging and reboots. Run with `--default` to
restore the factory buzzer behaviour.

### Options

| Option            | Description                                                              |
|-------------------|--------------------------------------------------------------------------|
| `--insert on/off` | bit 3: beep on card insertion                                            |
| `--remove on/off` | bit 4: beep on card removal (needs bit 3)                                |
| `--poweron on/off`| bit 5: beep at reader power-on                                           |
| `--silent`        | clear bits 3, 4 and 5                                                    |
| `--default`       | set bits 3, 4 and 5                                                      |
| `--reader TEXT`   | substring of the PC/SC reader name to use (default: first ACR1252 PICC)  |
| `--list`          | list PC/SC readers and exit                                              |
| `--ctl N`         | `SCARD_CTL_CODE` function number (default 3500; generic libccid: 1)      |
| `--dry-run`       | compute and show the new value, do not write                             |
| `-v, --verbose`   | show raw command/response bytes                                          |

Exit codes: `0` ok, `1` error, `2` write verification failed.

## Troubleshooting

**`escape command failed`**

PC/SC escape commands are disabled by default in many CCID drivers.

- *Windows, Microsoft inbox CCID driver*: install the ACS driver, or enable escape commands via
  the `EscapeCommandEnable` registry value for the device.
- *macOS, built-in CCID driver*: Apple's `ifd-ccid.bundle` ships with escape commands
  disabled and System Integrity Protection prevents changing that. Install ACS's own
  driver (acsccid) instead; see [docs/macos-driver.md](docs/macos-driver.md) for the
  verified step-by-step. The default `--ctl 3500` is correct once it is installed.
- *Linux, generic libccid*: run with `--ctl 1` and enable escape commands by setting bit `0x01`
  of `ifdDriverOptions` in `/usr/lib/pcsc/drivers/ifd-ccid.bundle/Contents/Info.plist`
  (path varies by distribution), then restart `pcscd`.
- *With the ACS driver*: the default `--ctl 3500` is correct.

**`could not connect`**

The script first tries a direct connection (no tag required). If the driver refuses that, it
falls back to a shared connection, which needs an NFC tag lying on the reader. Put a tag on the
reader and try again.

**`no matching reader found`**

Run `--list` to see the reader names PC/SC reports and pass part of one with `--reader`.
The script prefers the `PICC` (contactless) interface and skips the `SAM` slot by default.

## Tests

The test suite stubs the PC/SC layer, so it runs without pyscard, without a PC/SC daemon
and without a reader attached. It covers the bit logic, reader selection, the escape
command framing, and full CLI runs against a simulated reader (including write
verification failures).

```sh
uv run --with pytest python -m pytest        # with uv
pip install pytest && python -m pytest       # with pip
```

## License

[MIT](LICENSE)
