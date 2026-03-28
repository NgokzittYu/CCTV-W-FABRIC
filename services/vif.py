"""
多模态融合视频完整性指纹 (VIF - Video Integrity Fingerprint) -> 简化为 GOP 级轻量视觉宽容指纹

提取 GOP 关键帧及采样帧的感知特征，进行 Mean Pooling 后 LSH 降维，输出定长鲁棒指纹 (256-bit Hex)。
彻底移除时序光流与语义耦合，确立 VIF_VERSION="v4"。
"""

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from config import SETTINGS

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────────────

_PHASH_FEAT_DIM = 576       # MobileNetV3-Small classifier=Identity() 输出维度
VIF_VERSION = SETTINGS.vif_version
VIF_SAMPLE_FRAMES = SETTINGS.vif_sample_frames

# ── VIFConfig ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class VIFConfig:
    """VIF 配置，从环境变量/配置读取。"""
    mode: str = field(default_factory=lambda: os.getenv("VIF_MODE", "fusion").strip().lower())
    output_length: int = 256  # 输出比特长度，固定 256-bit 以保持位宽协议不变


# ── 感知哈希特征提取 ──────────────────────────────────────────────────

def extract_phash_feature(keyframe: np.ndarray) -> Optional[np.ndarray]:
    """从帧提取全局视觉特征 (Global Average Pooling 后的 576 维特征)。"""
    try:
        from services.perceptual_hash import _get_deep_hasher
        feats = _get_deep_hasher().extract_visual_features(keyframe)
        if feats is not None and "global" in feats:
            return feats["global"]
    except Exception as e:
        logger.warning("VIF deep feature extraction failed: %s", e)

    return np.zeros(_PHASH_FEAT_DIM, dtype=np.float64)


# ── LSH 降维投影 ──────────────────────────────────────────────────────

class _VIFLSHProjector:
    _instance: Optional['_VIFLSHProjector'] = None
    _lock = threading.Lock()

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = np.random.RandomState(seed)
        self.proj_cache = {}
        self.cache_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> '_VIFLSHProjector':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _get_projection_matrix(self, input_dim: int, output_bits: int) -> np.ndarray:
        cache_key = f"{input_dim}_{output_bits}"
        with self.cache_lock:
            if cache_key not in self.proj_cache:
                self.proj_cache[cache_key] = self.rng.randn(output_bits, input_dim).astype(np.float64)
            return self.proj_cache[cache_key]

    def project(self, feature: np.ndarray, output_bits: int) -> str:
        input_dim = feature.shape[0]
        proj_matrix = self._get_projection_matrix(input_dim, output_bits)

        with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
            bits = (proj_matrix @ feature) > 0

        # 将比特数组转为整数再转十六进制
        value = 0
        for bit in bits:
            value = (value << 1) | int(bit)

        hex_len = output_bits // 4
        return f"{value:0{hex_len}x}"


# ── 主入口 ────────────────────────────────────────────────────────────

def compute_vif(
    gop_frames: List[np.ndarray],
    config: Optional[VIFConfig] = None,
) -> Optional[str]:
    """
    计算基于 Mean Pooling 的 GOP 级感知指纹 (VIF v4)。

    Args:
        gop_frames: GOP 帧列表 (BGR numpy 数组)。包含 I 帧及少量采样帧。
        config: VIF 配置

    Returns:
        固定长度十六进制字符串（64 字符 = 256 位），
        当 mode="off" 时返回 None
    """
    if config is None:
        config = VIFConfig()

    if config.mode == "off":
        return None

    if not gop_frames or len(gop_frames) == 0:
        logger.warning("compute_vif: no frames provided")
        return None

    # 对传入的所有帧（I 帧 + 采样帧）提取感知特征
    feats_list = []
    for frame in gop_frames:
        feat = extract_phash_feature(frame)
        if feat is not None:
            feats_list.append(feat)

    if not feats_list:
        return None

    # Mean Pooling
    pooled_feat = np.mean(feats_list, axis=0)
    
    # 归一化 (防除零)
    norm = np.linalg.norm(pooled_feat)
    if norm > 1e-8:
        pooled_feat = pooled_feat / norm

    # LSH 投影输出定宽哈希 (默认 256-bit = 64 Hex)
    return _VIFLSHProjector.get_instance().project(pooled_feat, config.output_length)
