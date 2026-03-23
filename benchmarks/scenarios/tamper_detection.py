"""
场景：篡改检测准确率。

比较 VIF / pHash / naive SHA-256 在不同篡改类型下的 TPR/FPR/F1。
"""

import logging
from typing import Any, Dict

import numpy as np

from benchmarks.baselines.naive_hash import compute_hash, detect_tamper
from benchmarks.config import BenchmarkConfig
from benchmarks.datasets import apply_tamper, generate_frame
from benchmarks.metrics import ClassificationMetrics

logger = logging.getLogger(__name__)

_NUM_SAMPLES = 100  # 每种篡改类型的样本数


def run(config: BenchmarkConfig) -> Dict[str, Any]:
    """运行篡改检测场景。"""
    w, h = config.resolutions.get("720p", (1280, 720))
    results = {}

    methods = {
        "naive_sha256": _test_naive,
        "phash": _test_phash,
        "vif_fusion": _test_vif,
    }

    for method_name, test_fn in methods.items():
        method_results = {}

        for tamper_type in config.tamper_types:
            metrics = test_fn(w, h, tamper_type)
            method_results[tamper_type] = metrics.to_dict()
            logger.info(
                f"  {method_name}/{tamper_type}: "
                f"TPR={metrics.tpr:.3f}, FPR={metrics.fpr:.3f}, F1={metrics.f1:.3f}"
            )

        # 计算总体指标
        overall = ClassificationMetrics()
        for tamper_type in config.tamper_types:
            m = method_results[tamper_type]
            overall.tp += m["tp"]
            overall.fp += m["fp"]
            overall.tn += m["tn"]
            overall.fn += m["fn"]

        method_results["overall"] = overall.to_dict()
        results[method_name] = method_results

    return {"tamper_detection": results}


def _test_naive(w: int, h: int, tamper_type: str) -> ClassificationMetrics:
    """测试纯 SHA-256 检测。"""
    metrics = ClassificationMetrics()

    for i in range(_NUM_SAMPLES):
        orig = generate_frame(w, h, seed=i)
        orig_hash = compute_hash(orig)

        # 正样本（篡改）
        tampered = apply_tamper(orig, tamper_type, intensity=0.5, seed=i + 10000)
        if detect_tamper(orig_hash, compute_hash(tampered)):
            metrics.tp += 1
        else:
            metrics.fn += 1

        # 负样本（未篡改 — 但模拟编码差异）
        reencoded = _simulate_reencode(orig, seed=i + 20000)
        if detect_tamper(orig_hash, compute_hash(reencoded)):
            metrics.fp += 1  # 误报：转码导致哈希变化
        else:
            metrics.tn += 1

    return metrics


def _test_phash(w: int, h: int, tamper_type: str) -> ClassificationMetrics:
    """测试感知哈希检测。"""
    from services.perceptual_hash import compute_phash, hamming_distance

    metrics = ClassificationMetrics()
    threshold = 10

    for i in range(_NUM_SAMPLES):
        orig = generate_frame(w, h, seed=i)
        orig_phash = compute_phash(orig)
        if orig_phash is None:
            continue

        # 正样本（篡改）
        tampered = apply_tamper(orig, tamper_type, intensity=0.5, seed=i + 10000)
        tam_phash = compute_phash(tampered)
        if tam_phash and hamming_distance(orig_phash, tam_phash) > threshold:
            metrics.tp += 1
        else:
            metrics.fn += 1

        # 负样本（轻微变化 — 不应检测为篡改）
        reencoded = _simulate_reencode(orig, seed=i + 20000)
        re_phash = compute_phash(reencoded)
        if re_phash and hamming_distance(orig_phash, re_phash) > threshold:
            metrics.fp += 1
        else:
            metrics.tn += 1

    return metrics


def _test_vif(w: int, h: int, tamper_type: str) -> ClassificationMetrics:
    """测试 VIF 融合指纹检测。"""
    import os
    os.environ.setdefault("VIF_MODE", "fusion")

    from services.vif import VIFConfig, compute_vif

    metrics = ClassificationMetrics()
    vif_config = VIFConfig(mode="fusion")

    for i in range(_NUM_SAMPLES):
        orig = generate_frame(w, h, seed=i)
        orig_vif = compute_vif([orig], vif_config)
        if orig_vif is None:
            continue

        # 正样本（篡改）
        tampered = apply_tamper(orig, tamper_type, intensity=0.5, seed=i + 10000)
        tam_vif = compute_vif([tampered], vif_config)
        if tam_vif and _vif_distance(orig_vif, tam_vif) > 0.3:
            metrics.tp += 1
        else:
            metrics.fn += 1

        # 负样本
        reencoded = _simulate_reencode(orig, seed=i + 20000)
        re_vif = compute_vif([reencoded], vif_config)
        if re_vif and _vif_distance(orig_vif, re_vif) > 0.3:
            metrics.fp += 1
        else:
            metrics.tn += 1

    return metrics


def _vif_distance(vif1: str, vif2: str) -> float:
    """计算两个 VIF 指纹的归一化 Hamming 距离。"""
    if len(vif1) != len(vif2):
        return 1.0
    bits1 = bin(int(vif1, 16))[2:].zfill(len(vif1) * 4)
    bits2 = bin(int(vif2, 16))[2:].zfill(len(vif2) * 4)
    diff = sum(b1 != b2 for b1, b2 in zip(bits1, bits2))
    return diff / len(bits1)


def _simulate_reencode(frame: np.ndarray, seed: int = 0) -> np.ndarray:
    """模拟视频转码：微小噪声（不应被判定为篡改）。"""
    rng = np.random.RandomState(seed)
    noise = rng.normal(0, 2, frame.shape)  # 极小噪声
    return np.clip(frame.astype(float) + noise, 0, 255).astype(np.uint8)
