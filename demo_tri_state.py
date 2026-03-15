#!/usr/bin/env python3
"""
三态验证演示脚本

演示如何使用感知哈希和三态验证器来区分：
- INTACT: 完全一致
- RE_ENCODED: 重新编码（如 JPEG 压缩）
- TAMPERED: 内容篡改
"""

import cv2
import hashlib
import numpy as np

from services.perceptual_hash import compute_phash, hamming_distance
from services.tri_state_verifier import TriStateVerifier
from config import SETTINGS


def main():
    print("=" * 60)
    print("三态验证演示")
    print("=" * 60)

    # 创建原始图像
    print("\n1. 创建原始图像 (64x64 随机图案)")
    np.random.seed(42)
    original_image = np.random.randint(0, 256, (64, 64, 3), dtype=np.uint8)
    original_sha256 = hashlib.sha256(original_image.tobytes()).hexdigest()
    original_phash = compute_phash(original_image)

    print(f"   SHA-256: {original_sha256[:16]}...")
    print(f"   pHash:   {original_phash}")

    # 初始化验证器
    verifier = TriStateVerifier(hamming_threshold=SETTINGS.phash_hamming_threshold)
    print(f"\n   验证器阈值: {SETTINGS.phash_hamming_threshold} bits")

    # 场景 1: 完全一致
    print("\n" + "-" * 60)
    print("场景 1: INTACT - 完全一致的图像")
    print("-" * 60)

    identical_image = original_image.copy()
    identical_sha256 = hashlib.sha256(identical_image.tobytes()).hexdigest()
    identical_phash = compute_phash(identical_image)

    result = verifier.verify(original_sha256, original_phash, identical_sha256, identical_phash)
    distance = hamming_distance(original_phash, identical_phash)

    print(f"SHA-256 匹配: {original_sha256 == identical_sha256}")
    print(f"pHash 距离:   {distance} bits")
    print(f"验证结果:     {result} ✓")

    # 场景 2: JPEG 重新编码
    print("\n" + "-" * 60)
    print("场景 2: RE_ENCODED - JPEG 压缩 (质量=60)")
    print("-" * 60)

    _, encoded = cv2.imencode(".jpg", original_image, [cv2.IMWRITE_JPEG_QUALITY, 60])
    reencoded_image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    reencoded_sha256 = hashlib.sha256(reencoded_image.tobytes()).hexdigest()
    reencoded_phash = compute_phash(reencoded_image)

    result = verifier.verify(original_sha256, original_phash, reencoded_sha256, reencoded_phash)
    distance = hamming_distance(original_phash, reencoded_phash)

    print(f"SHA-256 匹配: {original_sha256 == reencoded_sha256}")
    print(f"pHash 距离:   {distance} bits")
    print(f"验证结果:     {result} ✓")

    # 场景 3: 内容篡改
    print("\n" + "-" * 60)
    print("场景 3: TAMPERED - 完全不同的图像")
    print("-" * 60)

    np.random.seed(999)
    tampered_image = np.random.randint(0, 256, (64, 64, 3), dtype=np.uint8)
    tampered_sha256 = hashlib.sha256(tampered_image.tobytes()).hexdigest()
    tampered_phash = compute_phash(tampered_image)

    result = verifier.verify(original_sha256, original_phash, tampered_sha256, tampered_phash)
    distance = hamming_distance(original_phash, tampered_phash)

    print(f"SHA-256 匹配: {original_sha256 == tampered_sha256}")
    print(f"pHash 距离:   {distance} bits")
    print(f"验证结果:     {result} ✓")

    # 总结
    print("\n" + "=" * 60)
    print("总结")
    print("=" * 60)
    print(f"✓ INTACT:      SHA-256 匹配 → 无任何修改")
    print(f"✓ RE_ENCODED:  SHA-256 不匹配 + pHash 距离 ≤ {SETTINGS.phash_hamming_threshold} bits → 合法重编码")
    print(f"✓ TAMPERED:    SHA-256 不匹配 + pHash 距离 > {SETTINGS.phash_hamming_threshold} bits → 内容篡改")
    print("=" * 60)


if __name__ == "__main__":
    main()
