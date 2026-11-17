# macOS: enabling escape commands for the ACR1252U

On macOS the script fails out of the box:

```
$ uv run acr1252_buzzer.py --silent
reader         : ACS ACR1252 Dual Reader PICC
error: escape command failed: Invalid parameter given. (0x80100004)
```

This document explains why and how to fix it. Tested on macOS 27.2.1 with an
ACR1252U (USB `072F:223B`).

## Why it fails

- macOS drives the reader with Apple's bundled CCID driver
  (`/usr/libexec/SmartCardServices/drivers/ifd-ccid.bundle`, reported by
  `system_profiler SPSmartCardsDataType` as `fr.apdu.ccid.smartcardccid`).
- That driver ships with `ifdDriverOptions = 0x0000`, which disables PC/SC escape
  commands. The Info.plist is protected by System Integrity Protection, so it cannot
  be edited.
- The ACR1252U API manual (section 5.8, "Peripherals Control") states that reader
  configuration commands such as the LED/buzzer behaviour byte are only reachable via
  `SCardControl` with `SCARD_CTL_CODE(3500)`. There is no pseudo-APDU wrapper through
  `SCardTransmit` for them, so neither `--ctl 1` nor any script-side workaround helps.
  (`FF 00 40 ...` exists but only triggers a one-off beep; it does not change the stored
  setting.)

## Fix: install ACS's own driver (acsccid)

[acsccid](https://github.com/acshk/acsccid) is ACS's fork of the open-source CCID
driver. It handles control code 3500 unconditionally, so no plist editing is needed.
ACS publishes a signed, notarized macOS installer.

### 1. Download

Get the installer from SourceForge:

- <https://sourceforge.net/projects/acsccid/files/acsccid/1.1.13/acsccid_installer-1.1.13.dmg/download>

Version 1.1.13 (2025-11-17) has SHA-256

```
e85d62069686e3c2f4c158e811f45c9dad326da14fce91c8d3c0057937aae348
```

```sh
shasum -a 256 ~/Downloads/acsccid_installer-1.1.13.dmg
```

### 2. Verify the package

```sh
hdiutil attach -nobrowse ~/Downloads/acsccid_installer-1.1.13.dmg
pkgutil --check-signature /Volumes/acsccid_installer/acsccid_installer.pkg
spctl -a -t install -vv  /Volumes/acsccid_installer/acsccid_installer.pkg
```

Expected: `Developer ID Installer: Advanced Card Systems Limited (4C5LG9ZP6A)`,
`Notarization: trusted by the Apple notary service`, `accepted`.

What the package does (inspected with `pkgutil --expand-full`):

- installs `/usr/local/libexec/SmartCardServices/drivers/ifd-acsccid.bundle`
  (universal arm64 + x86_64, lists ACR1252U PIDs `223B`, `223E`, `2244`, `226B`)
- its postinstall tries to symlink the bundle into `/usr/libexec/...`; that path is
  SIP-protected so the link silently fails. Harmless.
- two legacy sub-packages ("Apple CCID Driver Fix", "pcscd autostart") are skipped on
  macOS 10.11 and later
- flagged `RequireRestart`

### 3. Install

Either double-click `acsccid_installer.pkg` in the mounted image, or:

```sh
sudo installer -pkg /Volumes/acsccid_installer/acsccid_installer.pkg -target /
```

Then unplug and replug the reader. If the driver is still not picked up, reboot.

### 4. Verify the driver is in use

```sh
system_profiler SPSmartCardsDataType
```

"Reader Drivers" should now list `ifd-acsccid.bundle` under
`/usr/local/libexec/SmartCardServices/drivers`. If it still shows Apple's
`ifd-ccid.bundle`, macOS kept its built-in driver. `man 7 SmartCardServices` documents a
global preference to prefer third-party IFD drivers:

```sh
sudo defaults write /Library/Preferences/com.apple.security.smartcard useIFDCCID -bool yes
```

Replug the reader (or reboot) and check `system_profiler` again.

### 5. Test

```sh
uv run acr1252_buzzer.py              # read-only, should print the behaviour byte
uv run acr1252_buzzer.py --silent     # write; verifies by reading back
```

The default `--ctl 3500` is correct with acsccid.

## Uninstall

The disk image also contains `acsccid_uninstaller.pkg`. Running it removes the bundle
from `/usr/local/libexec/SmartCardServices/drivers/`. Replug the reader afterwards and
macOS falls back to its own driver. If you set `useIFDCCID`, undo it with:

```sh
sudo defaults delete /Library/Preferences/com.apple.security.smartcard useIFDCCID
```

## References

- [pcsclite-muscle thread: ACR1252U escape commands fail on macOS](https://lists.infradead.org/pipermail/pcsclite-muscle/2023-June/001357.html)
- [acsccid source on GitHub](https://github.com/acshk/acsccid) (`src/ifdhandler.c`,
  `IOCTL_CCID_ESCAPE` branch)
- [acsccid releases on SourceForge](https://sourceforge.net/projects/acsccid/files/acsccid/)
- [ACR1252U API manual](https://acs.comitex.net/wp-content/uploads/2016/07/API-ACR1252U-1.08.pdf)
