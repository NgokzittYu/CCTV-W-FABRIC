"""
Baseline: 纯 SHA-256 哈希检测。

只用密码学哈希，不使用感知哈希 — 任何编码变化都会报篡改。
"""

import hashlib

import numpy as np


def compute_hash(frame: np.ndarray) -> str:
    """对帧像素计算 SHA-256。"""
    return hashlib.sha256(frame.tobytes()).hexdigest()


def detect_tamper(original_hash: str, current_hash: str) -> bool:
    """纯哈希对比：不一致即判定篡改。"""
    return original_hash != current_hash
