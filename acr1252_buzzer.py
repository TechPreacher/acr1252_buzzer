#!/usr/bin/env python3
# /// script
# requires-python = ">=3.8"
# dependencies = ["pyscard>=2.0"]
# ///
"""
acr1252_buzzer.py - read / change the buzzer behaviour bits of an ACS ACR1252U.

The reader keeps one "LED and Buzzer Status Indicator Behavior" byte in
non-volatile memory (ACR1252U API manual v1.17, sections 5.4.5 / 5.4.6):

    read : E0 00 00 21 00        -> E1 00 00 00 01 <byte>
    write: E0 00 00 21 01 <byte> -> E1 00 00 00 01 <byte>

    bit 3 (0x08)  beep on card insertion
    bit 4 (0x10)  beep on card removal   (only effective if bit 3 is set)
    bit 5 (0x20)  beep at reader power-on
    bits 0-2,6,7  LED behaviour          (never touched by this script)

Factory default is 0x7F.

Requires pyscard:  pip install pyscard   (or just: uv run acr1252_buzzer.py)

Examples
    acr1252_buzzer.py                      show current setting
    acr1252_buzzer.py --silent             clear bits 3, 4 and 5
    acr1252_buzzer.py --insert off         clear bit 3 only
    acr1252_buzzer.py --insert on --remove off --poweron off
    acr1252_buzzer.py --default            set bits 3, 4 and 5 again
    acr1252_buzzer.py --list               list PC/SC readers
    acr1252_buzzer.py --silent --dry-run   show what would be written
"""

import argparse
import sys

from smartcard.scard import (
    SCARD_CTL_CODE,
    SCARD_LEAVE_CARD,
    SCARD_PROTOCOL_T0,
    SCARD_PROTOCOL_T1,
    SCARD_S_SUCCESS,
    SCARD_SCOPE_USER,
    SCARD_SHARE_DIRECT,
    SCARD_SHARE_SHARED,
    SCardConnect,
    SCardControl,
    SCardDisconnect,
    SCardEstablishContext,
    SCardGetErrorMessage,
    SCardListReaders,
    SCardReleaseContext,
)

BIT_INSERT = 0x08   # bit 3
BIT_REMOVE = 0x10   # bit 4
BIT_POWERON = 0x20  # bit 5
BUZZER_MASK = BIT_INSERT | BIT_REMOVE | BIT_POWERON

CMD_READ = [0xE0, 0x00, 0x00, 0x21, 0x00]
CMD_WRITE = [0xE0, 0x00, 0x00, 0x21, 0x01]
RESP_HEADER = [0xE1, 0x00, 0x00, 0x00, 0x01]

DEFAULT_CTL_FUNCTION = 3500  # ACS drivers; generic libccid uses 1


def hexs(data):
    return " ".join(f"{b:02X}" for b in data)


def die(msg, code=1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def check(hresult, what):
    if hresult != SCARD_S_SUCCESS:
        die(f"{what}: {SCardGetErrorMessage(hresult)} (0x{hresult & 0xFFFFFFFF:08X})")


def pick_reader(names, wanted):
    """Return the reader name to use, or None."""
    if wanted:
        hits = [n for n in names if wanted.lower() in n.lower()]
        return hits[0] if hits else None
    acr = [n for n in names if "ACR1252" in n.upper()]
    for n in acr:                       # prefer the contactless interface
        if "PICC" in n.upper():
            return n
    for n in acr:                       # otherwise anything that is not the SAM slot
        if "SAM" not in n.upper():
            return n
    return acr[0] if acr else None


def connect(hcontext, reader):
    """Connect without needing a tag on the reader if at all possible."""
    attempts = (
        (SCARD_SHARE_DIRECT, 0, "direct, no protocol"),
        (SCARD_SHARE_DIRECT, SCARD_PROTOCOL_T0 | SCARD_PROTOCOL_T1, "direct, T=0|T=1"),
        (SCARD_SHARE_SHARED, SCARD_PROTOCOL_T0 | SCARD_PROTOCOL_T1, "shared (needs a tag on the reader)"),
    )
    last = None
    for mode, proto, _label in attempts:
        hresult, hcard, _active = SCardConnect(hcontext, reader, mode, proto)
        if hresult == SCARD_S_SUCCESS:
            return hcard
        last = hresult
    die(
        f"could not connect to '{reader}': {SCardGetErrorMessage(last)}\n"
        "       try again with a tag lying on the reader"
    )


def escape(hcard, ctl, cmd, verbose):
    if verbose:
        print(f"  > {hexs(cmd)}")
    hresult, resp = SCardControl(hcard, ctl, cmd)
    if hresult != SCARD_S_SUCCESS:
        die(
            f"escape command failed: {SCardGetErrorMessage(hresult)} "
            f"(0x{hresult & 0xFFFFFFFF:08X})\n"
            "       - Windows + Microsoft inbox CCID driver: escape commands must be enabled\n"
            "         (EscapeCommandEnable) or the ACS driver installed\n"
            "       - Linux/macOS + generic libccid: try --ctl 1 and enable\n"
            "         ifdDriverOptions bit 0x01 in the driver's Info.plist"
        )
    resp = list(resp)
    if verbose:
        print(f"  < {hexs(resp)}")
    if len(resp) != 6 or resp[:5] != RESP_HEADER:
        die(f"unexpected response: {hexs(resp) or '(empty)'}")
    return resp[5]


def describe(value):
    def onoff(mask):
        return "on " if value & mask else "off"

    lines = [
        f"behaviour byte : 0x{value:02X}  (0b{value:08b})",
        f"  bit 3  beep on insertion : {onoff(BIT_INSERT)}",
        f"  bit 4  beep on removal   : {onoff(BIT_REMOVE)}",
        f"  bit 5  beep at power-on  : {onoff(BIT_POWERON)}",
    ]
    if value & BIT_REMOVE and not value & BIT_INSERT:
        lines.append("  note: bit 4 has no effect while bit 3 is clear")
    return "\n".join(lines)


def apply_args(current, args):
    new = current
    if args.silent:
        new &= ~BUZZER_MASK
    if args.default:
        new |= BUZZER_MASK
    for choice, mask in (
        (args.insert, BIT_INSERT),
        (args.remove, BIT_REMOVE),
        (args.poweron, BIT_POWERON),
    ):
        if choice == "on":
            new |= mask
        elif choice == "off":
            new &= ~mask
    return new & 0xFF


def main():
    p = argparse.ArgumentParser(
        description="Read or change the buzzer bits (3, 4, 5) of an ACS ACR1252U.",
        epilog="Without any change option the current setting is only displayed.",
    )
    p.add_argument("--insert", choices=("on", "off"), help="bit 3: beep on card insertion")
    p.add_argument("--remove", choices=("on", "off"), help="bit 4: beep on card removal (needs bit 3)")
    p.add_argument("--poweron", choices=("on", "off"), help="bit 5: beep at reader power-on")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--silent", action="store_true", help="clear bits 3, 4 and 5")
    g.add_argument("--default", action="store_true", help="set bits 3, 4 and 5")
    p.add_argument("--reader", metavar="TEXT", help="substring of the PC/SC reader name to use")
    p.add_argument("--list", action="store_true", help="list PC/SC readers and exit")
    p.add_argument(
        "--ctl",
        type=int,
        default=DEFAULT_CTL_FUNCTION,
        metavar="N",
        help=f"SCARD_CTL_CODE function number (default {DEFAULT_CTL_FUNCTION}; generic libccid: 1)",
    )
    p.add_argument("--dry-run", action="store_true", help="read and show the new value, do not write")
    p.add_argument("-v", "--verbose", action="store_true", help="show raw command/response bytes")
    args = p.parse_args()

    hresult, hcontext = SCardEstablishContext(SCARD_SCOPE_USER)
    check(hresult, "SCardEstablishContext")
    try:
        hresult, names = SCardListReaders(hcontext, [])
        check(hresult, "SCardListReaders")

        if args.list:
            for n in names:
                print(n)
            if not names:
                print("(no readers)")
            return

        reader = pick_reader(names, args.reader)
        if reader is None:
            die(
                "no matching reader found. Readers present:\n       "
                + ("\n       ".join(names) if names else "(none)")
                + "\n       use --reader TEXT to select one"
            )
        print(f"reader         : {reader}")

        hcard = connect(hcontext, reader)
        try:
            ctl = SCARD_CTL_CODE(args.ctl)
            current = escape(hcard, ctl, CMD_READ, args.verbose)
            print(describe(current))

            new = apply_args(current, args)
            wants_change = (
                args.silent
                or args.default
                or any(x is not None for x in (args.insert, args.remove, args.poweron))
            )
            if not wants_change:
                return
            if new == current:
                print("\nalready set as requested, nothing written")
                return
            if (new & BIT_REMOVE) and not (new & BIT_INSERT):
                print(
                    "\nwarning: bit 4 (removal beep) is set while bit 3 (insertion beep) is clear;\n"
                    "         per the manual bit 4 only works with bit 3 enabled",
                    file=sys.stderr,
                )
            if args.dry_run:
                print(f"\ndry run, would write 0x{new:02X}:")
                print(describe(new))
                return

            echoed = escape(hcard, ctl, CMD_WRITE + [new], args.verbose)
            verify = escape(hcard, ctl, CMD_READ, args.verbose)
            print("\nafter write:")
            print(describe(verify))
            if verify != new or echoed != new:
                die(
                    f"verification failed: wrote 0x{new:02X}, "
                    f"write echoed 0x{echoed:02X}, read back 0x{verify:02X}",
                    code=2,
                )
            print("ok (stored in the reader's non-volatile memory)")
        finally:
            SCardDisconnect(hcard, SCARD_LEAVE_CARD)
    finally:
        SCardReleaseContext(hcontext)


if __name__ == "__main__":
    main()
