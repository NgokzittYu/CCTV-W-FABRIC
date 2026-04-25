import pytest

from services.tri_state_verifier import TriStateVerifier, hex_bit_hamming


pytestmark = pytest.mark.unit


def test_intact_when_sha_matches(fixed_vifs):
    verifier = TriStateVerifier()

    status, risk, details = verifier.verify("a" * 64, "a" * 64, fixed_vifs["zero"], fixed_vifs["all"])

    assert status == "INTACT"
    assert risk == 0.0
    assert details["state_desc"] == "INTACT"


def test_re_encoded_when_sha_differs_but_vif_is_close(fixed_vifs):
    verifier = TriStateVerifier(tolerant_threshold=0.35)

    status, risk, details = verifier.verify("a" * 64, "b" * 64, fixed_vifs["zero"], fixed_vifs["one_bit"])

    assert status == "RE_ENCODED"
    assert risk < 0.35
    assert details["state_desc"] == "RE_ENCODED"
    assert details["vif_version"] == "v4"


def test_tampered_suspect_when_vif_distance_crosses_threshold(fixed_vifs):
    verifier = TriStateVerifier(tolerant_threshold=0.35)

    status, risk, details = verifier.verify("a" * 64, "b" * 64, fixed_vifs["zero"], fixed_vifs["half"])

    assert status == "TAMPERED"
    assert risk >= 0.35
    assert details["state_desc"] == "TAMPERED_SUSPECT"


@pytest.mark.parametrize("orig_vif,curr_vif,reason", [(None, "0" * 64, "vif_missing"), ("0" * 63, "0" * 64, "vif_format_invalid")])
def test_missing_or_invalid_vif_is_high_risk(orig_vif, curr_vif, reason):
    verifier = TriStateVerifier()

    status, risk, details = verifier.verify("a" * 64, "b" * 64, orig_vif, curr_vif)

    assert status == "TAMPERED"
    assert risk == 1.0
    assert details["reason"] == reason
    assert details["state_desc"] == "TAMPERED_SUSPECT"


def test_hamming_distance_counts_bits():
    assert hex_bit_hamming("0", "0") == 0
    assert hex_bit_hamming("0", "f") == 4
    assert hex_bit_hamming("f0", "0f") == 8
