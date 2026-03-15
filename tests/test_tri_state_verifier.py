"""
Unit tests for tri-state verification service.

Tests the TriStateVerifier class with various scenarios:
- INTACT: SHA-256 and pHash both match
- RE_ENCODED: SHA-256 differs but pHash is similar
- TAMPERED: SHA-256 differs and pHash is significantly different
"""

import hashlib

import cv2
import numpy as np
import pytest

from services.perceptual_hash import compute_phash
from services.tri_state_verifier import TriStateVerifier


def _create_test_image(seed: int = 42, size: int = 64) -> np.ndarray:
    """Create a deterministic test image (BGR format)."""
    np.random.seed(seed)
    return np.random.randint(0, 256, (size, size, 3), dtype=np.uint8)


def test_tri_state_intact():
    """Test INTACT state: SHA-256 and pHash both match."""
    verifier = TriStateVerifier(hamming_threshold=10)

    # Same image, same hash
    image = _create_test_image(seed=1)
    sha256 = hashlib.sha256(image.tobytes()).hexdigest()
    phash = compute_phash(image)

    result = verifier.verify(sha256, phash, sha256, phash)
    assert result == "INTACT"


def test_tri_state_re_encoded():
    """Test RE_ENCODED state: SHA-256 differs but pHash is similar."""
    verifier = TriStateVerifier(hamming_threshold=10)

    # Original image
    original = _create_test_image(seed=1)
    original_sha256 = hashlib.sha256(original.tobytes()).hexdigest()
    original_phash = compute_phash(original)

    # JPEG re-encoded image
    _, encoded = cv2.imencode(".jpg", original, [cv2.IMWRITE_JPEG_QUALITY, 60])
    reencoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    reencoded_sha256 = hashlib.sha256(reencoded.tobytes()).hexdigest()
    reencoded_phash = compute_phash(reencoded)

    # SHA-256 should differ
    assert original_sha256 != reencoded_sha256

    # Verify tri-state result
    result = verifier.verify(original_sha256, original_phash, reencoded_sha256, reencoded_phash)
    assert result == "RE_ENCODED"


def test_tri_state_tampered():
    """Test TAMPERED state: SHA-256 differs and pHash is significantly different."""
    verifier = TriStateVerifier(hamming_threshold=10)

    # Original image
    image1 = _create_test_image(seed=1)
    sha256_1 = hashlib.sha256(image1.tobytes()).hexdigest()
    phash_1 = compute_phash(image1)

    # Completely different image
    image2 = _create_test_image(seed=999)
    sha256_2 = hashlib.sha256(image2.tobytes()).hexdigest()
    phash_2 = compute_phash(image2)

    # SHA-256 should differ
    assert sha256_1 != sha256_2

    # Verify tri-state result
    result = verifier.verify(sha256_1, phash_1, sha256_2, phash_2)
    assert result == "TAMPERED"


def test_tri_state_missing_phash_original():
    """Test fallback when original pHash is missing."""
    verifier = TriStateVerifier(hamming_threshold=10)

    image1 = _create_test_image(seed=1)
    image2 = _create_test_image(seed=2)

    sha256_1 = hashlib.sha256(image1.tobytes()).hexdigest()
    sha256_2 = hashlib.sha256(image2.tobytes()).hexdigest()
    phash_2 = compute_phash(image2)

    # Missing original pHash
    result = verifier.verify(sha256_1, None, sha256_2, phash_2)
    assert result == "TAMPERED"


def test_tri_state_missing_phash_current():
    """Test fallback when current pHash is missing."""
    verifier = TriStateVerifier(hamming_threshold=10)

    image1 = _create_test_image(seed=1)
    image2 = _create_test_image(seed=2)

    sha256_1 = hashlib.sha256(image1.tobytes()).hexdigest()
    phash_1 = compute_phash(image1)
    sha256_2 = hashlib.sha256(image2.tobytes()).hexdigest()

    # Missing current pHash
    result = verifier.verify(sha256_1, phash_1, sha256_2, None)
    assert result == "TAMPERED"


def test_tri_state_missing_both_phash():
    """Test fallback when both pHashes are missing."""
    verifier = TriStateVerifier(hamming_threshold=10)

    image1 = _create_test_image(seed=1)
    image2 = _create_test_image(seed=2)

    sha256_1 = hashlib.sha256(image1.tobytes()).hexdigest()
    sha256_2 = hashlib.sha256(image2.tobytes()).hexdigest()

    # Missing both pHashes
    result = verifier.verify(sha256_1, None, sha256_2, None)
    assert result == "TAMPERED"


def test_tri_state_missing_phash_but_sha256_match():
    """Test that SHA-256 match returns INTACT even with missing pHash."""
    verifier = TriStateVerifier(hamming_threshold=10)

    image = _create_test_image(seed=1)
    sha256 = hashlib.sha256(image.tobytes()).hexdigest()

    # SHA-256 matches, pHash missing
    result = verifier.verify(sha256, None, sha256, None)
    assert result == "INTACT"


def test_tri_state_threshold_boundary():
    """Test behavior at threshold boundary."""
    # Use very strict threshold
    verifier_strict = TriStateVerifier(hamming_threshold=1)

    original = _create_test_image(seed=1)
    original_sha256 = hashlib.sha256(original.tobytes()).hexdigest()
    original_phash = compute_phash(original)

    # JPEG compression
    _, encoded = cv2.imencode(".jpg", original, [cv2.IMWRITE_JPEG_QUALITY, 60])
    reencoded = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    reencoded_sha256 = hashlib.sha256(reencoded.tobytes()).hexdigest()
    reencoded_phash = compute_phash(reencoded)

    # With strict threshold, JPEG compression might be classified as TAMPERED
    result_strict = verifier_strict.verify(
        original_sha256, original_phash, reencoded_sha256, reencoded_phash
    )
    # Result could be either RE_ENCODED or TAMPERED depending on compression artifacts
    assert result_strict in ["RE_ENCODED", "TAMPERED"]

    # Use permissive threshold
    verifier_permissive = TriStateVerifier(hamming_threshold=20)
    result_permissive = verifier_permissive.verify(
        original_sha256, original_phash, reencoded_sha256, reencoded_phash
    )
    # With permissive threshold, should definitely be RE_ENCODED
    assert result_permissive == "RE_ENCODED"


def test_tri_state_invalid_threshold():
    """Test that invalid threshold raises ValueError."""
    with pytest.raises(ValueError):
        TriStateVerifier(hamming_threshold=-1)

    with pytest.raises(ValueError):
        TriStateVerifier(hamming_threshold=65)


def test_tri_state_invalid_hash_format():
    """Test that invalid hash format is handled gracefully."""
    verifier = TriStateVerifier(hamming_threshold=10)

    # Invalid pHash format
    result = verifier.verify("sha256_1", "invalid_phash", "sha256_2", "also_invalid")
    assert result == "TAMPERED"


def test_tri_state_default_threshold():
    """Test that default threshold is 10."""
    verifier = TriStateVerifier()
    assert verifier.hamming_threshold == 10
