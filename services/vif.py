"""
多模态融合视频完整性指纹 (VIF - Video Integrity Fingerprint)

融合两种特征模态生成统一的视频完整性标识：
- 感知哈希特征 (pHash/Visual): MobileNetV3-Small pool 后 576 维
- 时序特征 (Temporal): 帧间光流统计特征

通过 VIF_MODE 环境变量控制：off / phash_only / fusion
"""

import logging
import os
import threading
from dataclasses import dataclass, field
from typing import List, Optional

import cv2
import numpy as np
import torch

logger = logging.getLogger(__name__)

# ── 常量 ──────────────────────────────────────────────────────────────

_PHASH_FEAT_DIM = 576       # MobileNetV3-Small classifier=Identity() 输出维度
_TEMPORAL_STATS_PER_PAIR = 4  # 每对帧: mean_mag, mean_angle, std_mag, std_angle
_MAX_TEMPORAL_PAIRS = 24    # 最多保留的帧对数
_TEMPORAL_FEAT_DIM = _TEMPORAL_STATS_PER_PAIR * _MAX_TEMPORAL_PAIRS  # 96

_VIF_LSH_SEED = 2026


# ── VIFConfig ─────────────────────────────────────────────────────────

def _env_float(name: str, default: float) -> float:
    val = os.getenv(name)
    if val is None or not val.strip():
        return default
    try:
        return float(val.strip())
    except ValueError:
        return default


@dataclass(frozen=True)
class VIFConfig:
    """VIF 配置，从环境变量读取。"""
    mode: str = field(default_factory=lambda: os.getenv("VIF_MODE", "off").strip().lower())
    phash_weight: float = field(default_factory=lambda: _env_float("VIF_PHASH_WEIGHT", 0.5))
    temporal_weight: float = field(default_factory=lambda: _env_float("VIF_TEMPORAL_WEIGHT", 0.5))
    output_length: int = 256  # 输出比特长度


# ── 感知哈希特征提取 ──────────────────────────────────────────────────

def extract_phash_feature(keyframe: np.ndarray) -> Optional[dict]:
    """从帧提取全局和 2x2 局部视觉特征。"""
    try:
        from services.perceptual_hash import _get_deep_hasher
        feats = _get_deep_hasher().extract_visual_features(keyframe)
        if feats is not None and "global" in feats and "local" in feats:
            return feats
    except Exception as e:
        logger.warning("VIF deep feature extraction failed: %s", e)

    return {
        "global": np.zeros(_PHASH_FEAT_DIM, dtype=np.float64),
        "local": [np.zeros(_PHASH_FEAT_DIM, dtype=np.float64) for _ in range(4)]
    }


# (Semantic feature extraction function removed to clean up definition)


# ── 时序特征提取 ──────────────────────────────────────────────────────

def extract_temporal_feature(gop_frames: List[np.ndarray]) -> np.ndarray:
    """
    计算帧间光流统计特征。

    对相邻帧对计算 Farneback 稠密光流，提取每对的统计量：
    (mean_magnitude, mean_angle, std_magnitude, std_angle)

    Args:
        gop_frames: GOP 内多帧 BGR numpy 数组列表

    Returns:
        固定长度特征向量 (96 维 = 24 对 × 4 统计量)
    """
    output = np.zeros(_TEMPORAL_FEAT_DIM, dtype=np.float64)

    if gop_frames is None or len(gop_frames) < 2:
        return output

    stats_list = []
    
    # 【调优】强制统一缩放到固定尺寸 (320x240) 计算光流，消除分辨率变化带来的幅值尺度差异
    STANDARD_SIZE = (320, 240)
    
    prev_gray = cv2.cvtColor(cv2.resize(gop_frames[0], STANDARD_SIZE), cv2.COLOR_BGR2GRAY)

    for i in range(1, len(gop_frames)):
        if len(stats_list) >= _MAX_TEMPORAL_PAIRS:
            break

        curr_gray = cv2.cvtColor(cv2.resize(gop_frames[i], STANDARD_SIZE), cv2.COLOR_BGR2GRAY)

        try:
            flow = cv2.calcOpticalFlowFarneback(
                prev_gray, curr_gray,
                None,
                pyr_scale=0.5, levels=3, winsize=15,
                iterations=3, poly_n=5, poly_sigma=1.2,
                flags=0,
            )
            mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1])
            stats_list.extend([
                float(np.mean(mag)),
                float(np.mean(ang)),
                float(np.std(mag)),
                float(np.std(ang)),
            ])
        except Exception as e:
            logger.warning("Optical flow computation failed for frame pair %d: %s", i, e)
            stats_list.extend([0.0, 0.0, 0.0, 0.0])

        prev_gray = curr_gray

    feat_array = np.array(stats_list, dtype=np.float64)
    if feat_array.size > 0:
        norm = np.linalg.norm(feat_array)
        if norm > 1e-8:
            feat_array = feat_array / norm
            
        copy_len = min(feat_array.shape[0], _TEMPORAL_FEAT_DIM)
        output[:copy_len] = feat_array[:copy_len]

    return output


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

    def _get_projection_matrix(self, input_dim: int, output_bits: int, modality: str) -> np.ndarray:
        cache_key = f"{modality}_{input_dim}_{output_bits}"
        with self.cache_lock:
            if cache_key not in self.proj_cache:
                self.proj_cache[cache_key] = self.rng.randn(output_bits, input_dim).astype(np.float64)
            return self.proj_cache[cache_key]

    def project(self, feature: np.ndarray, output_bits: int, modality: str = "default") -> str:
        input_dim = feature.shape[0]
        proj_matrix = self._get_projection_matrix(input_dim, output_bits, modality)

        with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
            bits = (proj_matrix @ feature) > 0

        # 将比特数组转为整数再转十六进制
        value = 0
        for bit in bits:
            value = (value << 1) | int(bit)

        hex_len = output_bits // 4
        return f"{value:0{hex_len}x}"


def fuse_features_v2(
    vis_feats: dict,
    temporal_feat: np.ndarray,
) -> str:
    """
    两模态独立投影，拼接为 256-bit 指纹。
    局部网格特征(vis_feats["local"])在主协议中被抛弃，仅保留其作为消融代码的灵活性。

    输出格式：hash_vis_global(32hex) || hash_tem(32hex)
    总计 64 hex chars
    """
    projector = _VIFLSHProjector.get_instance()
    hash_vis = projector.project(vis_feats["global"], 128, modality="vis")
    hash_tem = projector.project(temporal_feat, 128, modality="tem")
    return hash_vis + hash_tem


def split_vif_hex(vif_hex: str):
    """
    将 VIF v2 hex 字符串拆分为视觉与时序模态哈希 (主线降级版)。

    Returns:
        (hash_vis, hash_tem)
        - 32hex=128bit, 32hex=128bit
    """
    if not vif_hex or len(vif_hex) < 64:
        return None, None
    return vif_hex[:32], vif_hex[32:64]


# ── 主入口 ────────────────────────────────────────────────────────────

def compute_vif(
    gop_frames: List[np.ndarray],
    config: Optional[VIFConfig] = None,
) -> Optional[str]:
    """
    计算多模态融合视频完整性指纹 (VIF)。

    Args:
        gop_frames: GOP 内多帧列表 (BGR numpy 数组)。
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

    keyframe = gop_frames[0]

    if config.mode == "phash_only":
        feats = extract_phash_feature(keyframe)
        return _VIFLSHProjector.get_instance().project(feats["global"], config.output_length)

    if config.mode == "fusion":
        vis_feats = extract_phash_feature(keyframe)
        temporal_feat = extract_temporal_feature(gop_frames)

        return fuse_features_v2(vis_feats, temporal_feat)

    logger.warning("Unknown VIF_MODE=%s, returning None", config.mode)
    return None
