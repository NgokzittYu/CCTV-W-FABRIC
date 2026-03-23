"""
多模态融合视频完整性指纹 (VIF - Video Integrity Fingerprint)

融合三种特征模态生成统一的视频完整性标识：
- 感知哈希特征 (pHash): MobileNetV3-Small pool 后 576 维
- 语义特征 (Semantic): MobileNetV3-Small pool 前空间特征 + GAP
- 时序特征 (Temporal): 帧间光流统计特征

通过 VIF_MODE 环境变量控制：off / phash_only / semantic_only / fusion
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
_SEMANTIC_FEAT_DIM = 576    # 语义特征统一到相同维度（截断/填充）
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
    phash_weight: float = field(default_factory=lambda: _env_float("VIF_PHASH_WEIGHT", 0.4))
    semantic_weight: float = field(default_factory=lambda: _env_float("VIF_SEMANTIC_WEIGHT", 0.35))
    temporal_weight: float = field(default_factory=lambda: _env_float("VIF_TEMPORAL_WEIGHT", 0.25))
    output_length: int = 256  # 输出比特长度


# ── 感知哈希特征提取 ──────────────────────────────────────────────────

# 复用 perceptual_hash.py 中已有的 DeepPerceptualHasher 单例
def extract_phash_feature(frame: np.ndarray) -> np.ndarray:
    """
    从关键帧提取感知哈希特征向量 (pool 后 576 维)。

    复用 perceptual_hash.py 中的 DeepPerceptualHasher。
    失败时返回零向量（graceful degradation）。
    """
    try:
        from services.perceptual_hash import _get_deep_hasher
        feature = _get_deep_hasher().extract(frame)
        if feature is not None and feature.shape == (_PHASH_FEAT_DIM,):
            return feature
    except Exception as e:
        logger.warning("VIF phash feature extraction failed: %s", e)

    return np.zeros(_PHASH_FEAT_DIM, dtype=np.float64)


# ── 语义特征提取 ──────────────────────────────────────────────────────

class _SemanticFeatureExtractor:
    """
    独立的语义特征提取器。

    使用 MobileNetV3-Small 的 features 层（pool 前）提取空间特征图，
    经全局平均池化 (GAP) 后得到特征向量，与 phash 分支使用不同层特征。
    """
    _instance: Optional["_SemanticFeatureExtractor"] = None
    _lock = threading.Lock()

    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._model: Optional[torch.nn.Module] = None
        self._transform = None
        self._model_lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "_SemanticFeatureExtractor":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _load_model(self) -> torch.nn.Module:
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    from torchvision import transforms
                    from torchvision.models import MobileNet_V3_Small_Weights, mobilenet_v3_small

                    weights = MobileNet_V3_Small_Weights.DEFAULT
                    full_model = mobilenet_v3_small(weights=weights)
                    full_model.eval()

                    # 只保留 features 层（pool 前的卷积骨干）
                    self._model = full_model.features
                    self._model.eval()
                    self._model.to(self.device)

                    self._transform = transforms.Compose([
                        transforms.Resize(256),
                        transforms.CenterCrop(224),
                        transforms.ToTensor(),
                        transforms.Normalize(
                            mean=[0.485, 0.456, 0.406],
                            std=[0.229, 0.224, 0.225],
                        ),
                    ])
                    logger.info("VIF semantic feature extractor loaded on %s", self.device)
        return self._model

    @torch.no_grad()
    def extract(self, frame: np.ndarray) -> np.ndarray:
        """
        提取 pool 前空间特征图 → GAP → 截断/填充到 576 维 → L2 归一化。
        """
        from PIL import Image

        if frame is None or frame.size == 0 or len(frame.shape) != 3:
            return np.zeros(_SEMANTIC_FEAT_DIM, dtype=np.float64)

        try:
            # BGR → RGB → PIL
            rgb = frame[:, :, ::-1]
            pil_image = Image.fromarray(rgb, mode="RGB")

            model = self._load_model()
            tensor = self._transform(pil_image).unsqueeze(0).to(self.device)

            with self._model_lock:
                features_map = model(tensor)  # (1, C, H, W)

            # 全局平均池化 → (C,)
            gap = features_map.mean(dim=[2, 3]).squeeze(0)
            vector = gap.detach().cpu().numpy().astype(np.float64)

            # 截断或填充到 _SEMANTIC_FEAT_DIM
            if vector.shape[0] >= _SEMANTIC_FEAT_DIM:
                vector = vector[:_SEMANTIC_FEAT_DIM]
            else:
                vector = np.pad(vector, (0, _SEMANTIC_FEAT_DIM - vector.shape[0]))

            # L2 归一化
            norm = np.linalg.norm(vector)
            if norm > 1e-8:
                vector = vector / norm

            return vector
        except Exception as e:
            logger.warning("VIF semantic feature extraction failed: %s", e)
            return np.zeros(_SEMANTIC_FEAT_DIM, dtype=np.float64)


def extract_semantic_feature(frame: np.ndarray) -> np.ndarray:
    """从帧提取语义特征（pool 前 + GAP），576 维。"""
    return _SemanticFeatureExtractor.get_instance().extract(frame)


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
    prev_gray = cv2.cvtColor(gop_frames[0], cv2.COLOR_BGR2GRAY)

    for i in range(1, len(gop_frames)):
        if len(stats_list) >= _MAX_TEMPORAL_PAIRS:
            break

        curr_gray = cv2.cvtColor(gop_frames[i], cv2.COLOR_BGR2GRAY)

        # 调整尺寸一致
        if prev_gray.shape != curr_gray.shape:
            curr_gray = cv2.resize(curr_gray, (prev_gray.shape[1], prev_gray.shape[0]))

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

    # 填入 output 向量
    n = min(len(stats_list), _TEMPORAL_FEAT_DIM)
    output[:n] = stats_list[:n]

    return output


# ── 特征融合 ──────────────────────────────────────────────────────────

class _VIFLSHProjector:
    """VIF 专用 LSH 投影器，将融合特征降维到固定比特长度。"""

    _instance: Optional["_VIFLSHProjector"] = None
    _lock = threading.Lock()
    _matrices = {}  # input_dim -> projection_matrix 缓存

    @classmethod
    def get_instance(cls) -> "_VIFLSHProjector":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def project(self, feature: np.ndarray, output_bits: int) -> str:
        """将特征向量 LSH 投影到 output_bits 位，返回十六进制字符串。"""
        input_dim = feature.shape[0]
        key = (input_dim, output_bits)

        if key not in self._matrices:
            rng = np.random.RandomState(_VIF_LSH_SEED)
            self._matrices[key] = rng.randn(output_bits, input_dim).astype(np.float64)

        projection = self._matrices[key]
        with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
            bits = (projection @ feature) > 0

        # 将比特数组转为整数再转十六进制
        value = 0
        for bit in bits:
            value = (value << 1) | int(bit)

        hex_len = output_bits // 4
        return f"{value:0{hex_len}x}"


def fuse_features(
    phash_feat: np.ndarray,
    semantic_feat: np.ndarray,
    temporal_feat: np.ndarray,
    config: VIFConfig,
) -> str:
    """
    加权拼接三个特征向量，LSH 降维到固定长度。

    Returns:
        固定长度十六进制字符串 (output_length / 4 字符)
    """
    # 加权
    weighted_phash = phash_feat * config.phash_weight
    weighted_semantic = semantic_feat * config.semantic_weight
    weighted_temporal = temporal_feat * config.temporal_weight

    # 拼接
    fused = np.concatenate([weighted_phash, weighted_semantic, weighted_temporal])

    # LSH 投影
    return _VIFLSHProjector.get_instance().project(fused, config.output_length)


# ── 主入口 ────────────────────────────────────────────────────────────

def compute_vif(
    gop_frames: List[np.ndarray],
    config: Optional[VIFConfig] = None,
) -> Optional[str]:
    """
    计算多模态融合视频完整性指纹 (VIF)。

    Args:
        gop_frames: GOP 内多帧列表 (BGR numpy 数组)。
                    至少需要 1 帧用于 phash/semantic，>= 2 帧用于时序特征。
        config: VIF 配置，默认从环境变量自动读取

    Returns:
        固定长度十六进制字符串（如 64 字符 = 256 位），
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
        feat = extract_phash_feature(keyframe)
        return _VIFLSHProjector.get_instance().project(feat, config.output_length)

    if config.mode == "semantic_only":
        feat = extract_semantic_feature(keyframe)
        return _VIFLSHProjector.get_instance().project(feat, config.output_length)

    if config.mode == "fusion":
        phash_feat = extract_phash_feature(keyframe)
        semantic_feat = extract_semantic_feature(keyframe)
        temporal_feat = extract_temporal_feature(gop_frames)
        return fuse_features(phash_feat, semantic_feat, temporal_feat, config)

    logger.warning("Unknown VIF_MODE=%s, returning None", config.mode)
    return None
