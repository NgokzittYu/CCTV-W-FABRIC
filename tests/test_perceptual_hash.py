"""
Unit tests for perceptual hash service.

Tests the compute_phash() and hamming_distance() functions with various
image inputs including identical images, JPEG-compressed images, and
completely different images.
"""

import hashlib

import cv2
import numpy as np
import pytest

from services.perceptual_hash import compute_phash, hamming_distance


def _create_test_image(seed: int = 42, size: int = 64) -> np.ndarray:
    """Create a deterministic test image (BGR format)."""
    np.random.seed(seed)
    return np.random.randint(0, 256, (size, size, 3), dtype=np.uint8)


def test_compute_phash_basic():
    """Test that pHash computation returns a valid hex string."""
    image = _create_test_image(seed=1)
    phash = compute_phash(image)

    assert phash is not None
    assert isinstance(phash, str)
    assert len(phash) == 16  # 64 bits = 16 hex chars
    assert all(c in "0123456789abcdef" for c in phash)


def test_compute_phash_identical_images():
    """Test that identical images produce identical pHashes."""
    image1 = _create_test_image(seed=1)
    image2 = image1.copy()

    phash1 = compute_phash(image1)
    phash2 = compute_phash(image2)

    assert phash1 == phash2
    assert hamming_distance(phash1, phash2) == 0


def test_compute_phash_jpeg_compression():
    """Test that JPEG compression produces similar pHash (small Hamming distance)."""
    original = _create_test_image(seed=1)
    phash_original = compute_phash(original)

    # Simulate JPEG compression
    _, encoded = cv2.imencode(".jpg", original, [cv2.IMWRITE_JPEG_QUALITY, 60])
    compressed = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    phash_compressed = compute_phash(compressed)

    distance = hamming_distance(phash_original, phash_compressed)

    # JPEG compression should produce small Hamming distance (typically 0-5 bits)
    assert distance <= 10, f"JPEG compression distance too large: {distance}"


def test_compute_phash_different_images():
    """Test that completely different images produce different pHashes."""
    image1 = _create_test_image(seed=1)
    image2 = _create_test_image(seed=999)

    phash1 = compute_phash(image1)
    phash2 = compute_phash(image2)

    distance = hamming_distance(phash1, phash2)

    # Different images should have large Hamming distance (typically 20+ bits)
    assert distance > 15, f"Different images too similar: {distance}"


def test_compute_phash_none_input():
    """Test that None input returns None."""
    result = compute_phash(None)
    assert result is None


def test_compute_phash_empty_array():
    """Test that empty array returns None."""
    empty = np.array([])
    result = compute_phash(empty)
    assert result is None


def test_compute_phash_invalid_shape():
    """Test that invalid shape returns None."""
    # 2D array instead of 3D
    invalid = np.random.randint(0, 256, (64, 64), dtype=np.uint8)
    result = compute_phash(invalid)
    assert result is None


def test_hamming_distance_basic():
    """Test Hamming distance calculation."""
    # Create two images with known difference
    image1 = _create_test_image(seed=1)
    image2 = _create_test_image(seed=2)

    phash1 = compute_phash(image1)
    phash2 = compute_phash(image2)

    distance = hamming_distance(phash1, phash2)

    assert isinstance(distance, int)
    assert 0 <= distance <= 64  # Valid range for 64-bit hash


def test_hamming_distance_invalid_input():
    """Test that invalid hash inputs raise ValueError."""
    with pytest.raises(ValueError):
        hamming_distance("invalid", "also_invalid")

    with pytest.raises(ValueError):
        hamming_distance(None, "0123456789abcdef")

    with pytest.raises(ValueError):
        hamming_distance("0123456789abcdef", None)


def test_phash_deterministic():
    """Test that pHash computation is deterministic."""
    image = _create_test_image(seed=42)

    phash1 = compute_phash(image)
    phash2 = compute_phash(image)
    phash3 = compute_phash(image)

    assert phash1 == phash2 == phash3


def test_phash_different_sizes():
    """Test pHash with different image sizes."""
    small = _create_test_image(seed=1, size=32)
    medium = _create_test_image(seed=1, size=64)
    large = _create_test_image(seed=1, size=128)

    phash_small = compute_phash(small)
    phash_medium = compute_phash(medium)
    phash_large = compute_phash(large)

    # All should produce valid hashes
    assert phash_small is not None
    assert phash_medium is not None
    assert phash_large is not None

    # Different sizes with same seed should produce similar (but not identical) hashes
    # This is expected behavior for pHash
    assert len(phash_small) == len(phash_medium) == len(phash_large) == 16
