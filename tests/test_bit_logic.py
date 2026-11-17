"""Pure bit-twiddling: apply_args, describe, hexs."""

import pytest

from conftest import make_args

LED_BITS = 0b11000111  # bits 0-2, 6, 7 - must never be modified


@pytest.mark.parametrize(
    "current, flags, expected",
    [
        # --silent clears exactly bits 3,4,5 and leaves LED bits alone
        (0x7F, dict(silent=True), 0x47),
        (0xFF, dict(silent=True), 0xC7),
        (0x00, dict(silent=True), 0x00),
        # --default sets exactly bits 3,4,5
        (0x47, dict(default=True), 0x7F),
        (0x00, dict(default=True), 0x38),
        (0xC7, dict(default=True), 0xFF),
        # single bits
        (0x7F, dict(insert="off"), 0x77),
        (0x7F, dict(remove="off"), 0x6F),
        (0x7F, dict(poweron="off"), 0x5F),
        (0x47, dict(insert="on"), 0x4F),
        (0x47, dict(remove="on"), 0x57),
        (0x47, dict(poweron="on"), 0x67),
        # combinations
        (0x7F, dict(insert="on", remove="off", poweron="off"), 0x4F),
        # explicit bit flags are applied after --silent / --default
        (0x7F, dict(silent=True, insert="on"), 0x4F),
        (0x00, dict(default=True, poweron="off"), 0x18),
        # no flags: unchanged
        (0x5A, dict(), 0x5A),
    ],
)
def test_apply_args(mod, current, flags, expected):
    assert mod.apply_args(current, make_args(**flags)) == expected


@pytest.mark.parametrize("current", [0x00, 0x07, 0x38, 0x7F, 0xC7, 0xFF, 0xA5])
@pytest.mark.parametrize(
    "flags",
    [dict(silent=True), dict(default=True), dict(insert="off"), dict(remove="on", poweron="off")],
)
def test_apply_args_never_touches_led_bits(mod, current, flags):
    new = mod.apply_args(current, make_args(**flags))
    assert new & LED_BITS == current & LED_BITS
    assert 0 <= new <= 0xFF


def test_buzzer_mask_is_bits_3_4_5(mod):
    assert mod.BIT_INSERT == 1 << 3
    assert mod.BIT_REMOVE == 1 << 4
    assert mod.BIT_POWERON == 1 << 5
    assert mod.BUZZER_MASK == 0x38


def test_describe_all_on(mod):
    text = mod.describe(0x7F)
    assert "0x7F" in text and "0b01111111" in text
    assert "beep on insertion : on" in text
    assert "beep on removal   : on" in text
    assert "beep at power-on  : on" in text
    assert "note:" not in text


def test_describe_all_off(mod):
    text = mod.describe(0x47)
    assert "0x47" in text
    assert "insertion : off" in text
    assert "removal   : off" in text
    assert "power-on  : off" in text


def test_describe_warns_when_removal_set_without_insertion(mod):
    assert "bit 4 has no effect while bit 3 is clear" in mod.describe(0x10)
    assert "no effect" not in mod.describe(0x18)
    assert "no effect" not in mod.describe(0x08)


def test_hexs(mod):
    assert mod.hexs([0xE0, 0x00, 0x21, 0xFF]) == "E0 00 21 FF"
    assert mod.hexs([]) == ""
