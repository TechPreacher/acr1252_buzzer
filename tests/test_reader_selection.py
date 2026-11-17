"""pick_reader: choosing the right PC/SC reader name."""

PICC = "ACS ACR1252 1S CL Reader PICC 0"
SAM = "ACS ACR1252 1S CL Reader SAM 0"
OTHER = "Yubico YubiKey OTP+FIDO+CCID"


def test_prefers_picc_interface(mod):
    assert mod.pick_reader([SAM, PICC, OTHER], None) == PICC
    assert mod.pick_reader([PICC, SAM], None) == PICC


def test_avoids_sam_slot_when_no_picc(mod):
    plain = "ACS ACR1252 1S CL Reader 00"
    assert mod.pick_reader([SAM, plain], None) == plain


def test_falls_back_to_sam_if_only_acr_reader(mod):
    assert mod.pick_reader([SAM, OTHER], None) == SAM


def test_ignores_non_acr1252_readers(mod):
    assert mod.pick_reader([OTHER], None) is None
    assert mod.pick_reader([], None) is None


def test_explicit_substring_is_case_insensitive(mod):
    assert mod.pick_reader([PICC, SAM, OTHER], "sam") == SAM
    assert mod.pick_reader([PICC, SAM, OTHER], "YUBI") == OTHER


def test_explicit_substring_returns_first_hit(mod):
    assert mod.pick_reader([SAM, PICC], "acr1252") == SAM


def test_explicit_substring_no_match(mod):
    assert mod.pick_reader([PICC, SAM], "nope") is None
