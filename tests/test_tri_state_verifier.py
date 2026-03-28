"""
Unit tests for tri-state verification service.

Tests the TriStateVerifier class with various scenarios:
- INTACT: SHA-256 matches
- RE_ENCODED: SHA-256 differs but VIF risk score is below tampered threshold
- TAMPERED: SHA-256 differs and VIF risk score is above threshold
"""

import pytest

from services.tri_state_verifier import TriStateVerifier


def test_tri_state_intact():
    verifier = TriStateVerifier()
    sha = "a" * 64
    vif = "b" * 64
    state, risk, details = verifier.verify(sha, sha, vif, vif)
    assert state == "INTACT"
    assert risk == 0.0


def test_tri_state_no_vif_diff_sha():
    verifier = TriStateVerifier()
    sha1 = "a" * 64
    sha2 = "b" * 64
    # Without VIF, fallback to pure SHA-256 -> TAMPERED
    state, risk, details = verifier.verify(sha1, sha2, None, None)
    assert state == "TAMPERED"
    assert risk == 1.0


def test_tri_state_re_encoded():
    verifier = TriStateVerifier()
    sha1 = "a" * 64
    sha2 = "b" * 64
    
    # 256 bits = 64 hex chars. Let's make 2 bits different in visual.
    # visual is first 64 bits = 16 hex chars. 
    v1 = "0" * 64
    v2 = "3" + "0" * 63  # '3' is 0011, hamming dist is 2
    
    state, risk, details = verifier.verify(sha1, sha2, v1, v2)
    # risk should be small -> RE_ENCODED
    assert state == "RE_ENCODED"
    assert risk > 0.0
    assert risk < 0.5


def test_tri_state_tampered():
    verifier = TriStateVerifier()
    sha1 = "a" * 64
    sha2 = "b" * 64
    
    v1 = "0" * 64
    v2 = "f" * 64  # Max distance
    
    state, risk, details = verifier.verify(sha1, sha2, v1, v2)
    # risk should be 1.0 -> TAMPERED
    assert state == "TAMPERED"
    assert risk == 1.0
