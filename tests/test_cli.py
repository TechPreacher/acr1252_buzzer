"""End-to-end runs of main() against a FakeReader."""

import pytest

PICC = "ACS ACR1252 1S CL Reader PICC 0"
SAM = "ACS ACR1252 1S CL Reader SAM 0"


def test_no_flags_only_reads(fake_reader, run_main):
    r = fake_reader(value=0x7F)
    code, out, err = run_main()
    assert code == 0
    assert f"reader         : {PICC}" in out
    assert "0x7F" in out
    assert r.writes == []
    assert r.commands == [[0xE0, 0x00, 0x00, 0x21, 0x00]]


def test_silent_writes_and_verifies(fake_reader, run_main):
    r = fake_reader(value=0x7F)
    code, out, err = run_main("--silent")
    assert code == 0
    assert r.writes == [0x47]
    assert r.value == 0x47
    # read, write, read-back
    assert [c[4] for c in r.commands] == [0x00, 0x01, 0x00]
    assert "after write:" in out
    assert "0x47" in out
    assert "ok (stored" in out


def test_default_restores_buzzer_bits(fake_reader, run_main):
    r = fake_reader(value=0x47)
    code, out, _ = run_main("--default")
    assert code == 0
    assert r.value == 0x7F


def test_individual_flags(fake_reader, run_main):
    r = fake_reader(value=0x7F)
    code, _, _ = run_main("--insert", "on", "--remove", "off", "--poweron", "off")
    assert code == 0
    assert r.value == 0x4F


def test_led_bits_survive_a_write(fake_reader, run_main):
    r = fake_reader(value=0xFF)
    run_main("--silent")
    assert r.value == 0xC7


def test_nothing_written_when_already_set(fake_reader, run_main):
    r = fake_reader(value=0x47)
    code, out, _ = run_main("--silent")
    assert code == 0
    assert r.writes == []
    assert "already set as requested, nothing written" in out


def test_dry_run_does_not_write(fake_reader, run_main):
    r = fake_reader(value=0x7F)
    code, out, _ = run_main("--silent", "--dry-run")
    assert code == 0
    assert r.writes == []
    assert "dry run, would write 0x47" in out
    assert "insertion : off" in out


def test_verification_failure_exits_2(fake_reader, run_main):
    r = fake_reader(value=0x7F, lie_on_readback=0x7F)  # reader accepts write but reads back old value
    code, out, err = run_main("--silent")
    assert code == 2
    assert "verification failed" in err
    assert "wrote 0x47" in err and "read back 0x7F" in err


def test_removal_without_insertion_warns_but_writes(fake_reader, run_main):
    r = fake_reader(value=0x47)
    code, out, err = run_main("--remove", "on")
    assert code == 0
    assert r.value == 0x57
    assert "warning: bit 4" in err


def test_list_prints_readers_and_exits(fake_reader, run_main):
    r = fake_reader([PICC, SAM])
    code, out, _ = run_main("--list")
    assert code == 0
    assert out.splitlines() == [PICC, SAM]
    assert r.connected == 0
    assert r.released == 1


def test_list_with_no_readers(fake_reader, run_main):
    fake_reader([])
    code, out, _ = run_main("--list")
    assert code == 0
    assert "(no readers)" in out


def test_no_matching_reader(fake_reader, run_main):
    r = fake_reader(["Yubico YubiKey OTP+FIDO+CCID"])
    code, _, err = run_main()
    assert code == 1
    assert "no matching reader found" in err
    assert "Yubico" in err
    assert "--reader TEXT" in err
    assert r.released == 1


def test_reader_substring_selects_sam_slot(fake_reader, run_main):
    fake_reader([PICC, SAM])
    code, out, _ = run_main("--reader", "SAM")
    assert code == 0
    assert f"reader         : {SAM}" in out


def test_default_ctl_code_is_acs_3500(fake_reader, run_main, mod):
    r = fake_reader()
    run_main()
    assert r.ctl_codes == {mod.SCARD_CTL_CODE(3500)}


def test_ctl_override(fake_reader, run_main, mod):
    r = fake_reader()
    run_main("--ctl", "1")
    assert r.ctl_codes == {mod.SCARD_CTL_CODE(1)}


def test_falls_back_to_shared_connect(fake_reader, run_main, mod):
    r = fake_reader(direct_ok=False)
    code, _, _ = run_main()
    assert code == 0
    assert r.connect_modes[-1][0] == mod.SCARD_SHARE_SHARED


def test_handles_released_after_write(fake_reader, run_main):
    r = fake_reader(value=0x7F)
    run_main("--silent")
    assert r.connected == 1
    assert r.disconnected == 1
    assert r.released == 1


def test_handles_released_after_failure(fake_reader, run_main):
    r = fake_reader(value=0x7F, lie_on_readback=0x7F)
    run_main("--silent")
    assert r.disconnected == 1
    assert r.released == 1


def test_silent_and_default_are_mutually_exclusive(fake_reader, run_main):
    fake_reader()
    code, _, err = run_main("--silent", "--default")
    assert code == 2  # argparse usage error
    assert "not allowed with" in err


@pytest.mark.parametrize("flag", ["--insert", "--remove", "--poweron"])
def test_bit_flags_reject_bad_values(fake_reader, run_main, flag):
    fake_reader()
    code, _, err = run_main(flag, "maybe")
    assert code == 2
    assert "invalid choice" in err
