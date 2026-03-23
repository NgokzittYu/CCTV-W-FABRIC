import importlib

import numpy as np
import pytest
from PIL import Image, ImageDraw

import services.perceptual_hash as perceptual_hash


@pytest.fixture()
def phash_module(monkeypatch):
    monkeypatch.setenv("PHASH_MODE", "deep")
    module = importlib.reload(perceptual_hash)
    yield module
    monkeypatch.delenv("PHASH_MODE", raising=False)
    importlib.reload(module)


def _to_bgr(image: Image.Image) -> np.ndarray:
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    return rgb[:, :, ::-1].copy()


def _create_base_image(size: int = 256) -> np.ndarray:
    y, x = np.indices((size, size))
    image = np.zeros((size, size, 3), dtype=np.uint8)
    image[..., 0] = (x * 3 + y * 2) % 256
    image[..., 1] = (x * 5) % 256
    image[..., 2] = (y * 7) % 256

    pil_image = Image.fromarray(image, mode="RGB")
    draw = ImageDraw.Draw(pil_image)
    draw.rectangle((24, 24, size - 24, size - 24), outline=(40, 180, 220), width=4)
    draw.ellipse((size // 3 - size // 8, size // 3 - size // 8, size // 3 + size // 8, size // 3 + size // 8), fill=(230, 80, 60))
    draw.ellipse((size * 2 // 3 - size // 7, size * 2 // 3 - size // 7, size * 2 // 3 + size // 7, size * 2 // 3 + size // 7), fill=(80, 220, 80))
    draw.line((0, size // 2, size - 1, size // 2), fill=(255, 255, 255), width=3)
    draw.text((size // 4, size * 3 // 4), "SL", fill=(20, 20, 20))
    return _to_bgr(pil_image)


def _create_different_image(size: int = 256) -> np.ndarray:
    image = Image.new("RGB", (size, size), (25, 25, 25))
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, size - 20, size - 20), fill=(250, 250, 40))
    draw.line((0, 0, size - 1, size - 1), fill=(255, 0, 0), width=10)
    draw.line((0, size - 1, size - 1, 0), fill=(0, 0, 255), width=10)
    draw.text((size // 5, size // 2), "ALT", fill=(0, 80, 0))
    return _to_bgr(image)


def _jpeg_compress(image: np.ndarray, quality: int) -> np.ndarray:
    rgb_image = Image.fromarray(image[:, :, ::-1], mode="RGB")
    import io

    buffer = io.BytesIO()
    rgb_image.save(buffer, format="JPEG", quality=quality)
    buffer.seek(0)
    decoded = Image.open(buffer).convert("RGB")
    return _to_bgr(decoded)


def _resize_half_restore(image: np.ndarray) -> np.ndarray:
    rgb_image = Image.fromarray(image[:, :, ::-1], mode="RGB")
    width, height = rgb_image.size
    half = rgb_image.resize((width // 2, height // 2), Image.Resampling.BILINEAR)
    restored = half.resize((width, height), Image.Resampling.BILINEAR)
    return _to_bgr(restored)


def _add_gaussian_noise(image: np.ndarray, sigma: float) -> np.ndarray:
    rng = np.random.RandomState(42)
    noise = rng.normal(0, sigma, image.shape).astype(np.float32)
    noisy = np.clip(image.astype(np.float32) + noise, 0, 255)
    return noisy.astype(np.uint8)


def _compute_in_mode(mode: str, image: np.ndarray, monkeypatch) -> str:
    monkeypatch.setenv("PHASH_MODE", mode)
    module = importlib.reload(perceptual_hash)
    value = module.compute_phash(image)
    assert value is not None
    return value


def test_determinism(phash_module):
    image = _create_base_image()
    hash1 = phash_module.compute_phash(image)
    hash2 = phash_module.compute_phash(image)

    assert hash1 == hash2


def test_output_format(phash_module):
    image = _create_base_image()
    hash_value = phash_module.compute_phash(image)

    assert isinstance(hash_value, str)
    assert len(hash_value) == 16
    assert all(c in "0123456789abcdef" for c in hash_value)
    assert phash_module.hamming_distance(hash_value, hash_value) == 0


def test_robustness_vs_legacy(monkeypatch, capsys):
    original = _create_base_image()
    jpeg50 = _jpeg_compress(original, quality=50)
    scaled = _resize_half_restore(original)

    legacy_original = _compute_in_mode("legacy", original, monkeypatch)
    legacy_jpeg = _compute_in_mode("legacy", jpeg50, monkeypatch)
    legacy_scaled = _compute_in_mode("legacy", scaled, monkeypatch)

    deep_original = _compute_in_mode("deep", original, monkeypatch)
    deep_jpeg = _compute_in_mode("deep", jpeg50, monkeypatch)
    deep_scaled = _compute_in_mode("deep", scaled, monkeypatch)

    rows = [
        ("jpeg_q50", perceptual_hash.hamming_distance(legacy_original, legacy_jpeg), perceptual_hash.hamming_distance(deep_original, deep_jpeg)),
        ("scale_50pct", perceptual_hash.hamming_distance(legacy_original, legacy_scaled), perceptual_hash.hamming_distance(deep_original, deep_scaled)),
    ]

    print("scenario,legacy,deep")
    for name, legacy_distance, deep_distance in rows:
        print(f"{name},{legacy_distance},{deep_distance}")

    out = capsys.readouterr().out
    assert "scenario,legacy,deep" in out


def test_tamper_detection(phash_module):
    original = _create_base_image()
    different = _create_different_image()

    hash1 = phash_module.compute_phash(original)
    hash2 = phash_module.compute_phash(different)

    assert phash_module.hamming_distance(hash1, hash2) > 20


def test_transcoding_simulation(monkeypatch, capsys):
    original = _create_base_image()
    jpeg70 = _jpeg_compress(original, quality=70)
    noisy = _add_gaussian_noise(original, sigma=5)

    legacy_original = _compute_in_mode("legacy", original, monkeypatch)
    legacy_jpeg = _compute_in_mode("legacy", jpeg70, monkeypatch)
    legacy_noisy = _compute_in_mode("legacy", noisy, monkeypatch)

    deep_original = _compute_in_mode("deep", original, monkeypatch)
    deep_jpeg = _compute_in_mode("deep", jpeg70, monkeypatch)
    deep_noisy = _compute_in_mode("deep", noisy, monkeypatch)

    legacy_jpeg_distance = perceptual_hash.hamming_distance(legacy_original, legacy_jpeg)
    legacy_noisy_distance = perceptual_hash.hamming_distance(legacy_original, legacy_noisy)
    deep_jpeg_distance = perceptual_hash.hamming_distance(deep_original, deep_jpeg)
    deep_noisy_distance = perceptual_hash.hamming_distance(deep_original, deep_noisy)

    print("pair,legacy,deep")
    print(f"jpeg_q70,{legacy_jpeg_distance},{deep_jpeg_distance}")
    print(f"gaussian_sigma5,{legacy_noisy_distance},{deep_noisy_distance}")

    out = capsys.readouterr().out
    assert "pair,legacy,deep" in out
    assert deep_jpeg_distance <= 64
    assert deep_noisy_distance <= 64
