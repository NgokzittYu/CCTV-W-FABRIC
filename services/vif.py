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


# ── MV 特征维度 ──
_MV_GRID_N = 8
_MV_FEAT_DIM = _MV_GRID_N * _MV_GRID_N * 3  # 192


def extract_temporal_feature_mv(
    motion_vectors: list,
    frame_width: int,
    frame_height: int,
    fps: float = 30.0,
    grid_n: int = _MV_GRID_N,
) -> np.ndarray:
    """
    从 H.264/H.265 压缩域运动矢量提取 8×8 网格化时空特征。

    相比 Farneback 稠密光流：
    - 天然抗压缩：MV 是编码器自身的宏块预测，合法转码后宏观趋势不变
    - 零解码成本：直接从码流 side_data 读取，无需像素级计算
    - 覆盖全帧：每个 P/B 帧的所有预测宏块都有 MV

    特征设计：
    - 速度归一化：(dx/width)*fps，抗分辨率缩放 + 抗帧率变化
    - 面积加权：(w*h)/(W*H)，抗 H.265 动态宏块切分
    - 网格池化：8×8=64 区块，保留空间运动分布（避免正负抵消）

    Args:
        motion_vectors: PyAV frame.side_data MOTION_VECTORS 数据列表
                       每个元素需有属性: src_x, src_y, dst_x, dst_y, w, h
        frame_width: 视频帧宽度（像素）
        frame_height: 视频帧高度（像素）
        fps: 视频帧率（用于速度归一化）
        grid_n: 网格大小（默认 8×8）

    Returns:
        192 维特征向量 (8×8×3: abs_vel_x, abs_vel_y, magnitude)
    """
    grid = np.zeros((grid_n, grid_n, 4), dtype=np.float64)

    if not motion_vectors or frame_width <= 0 or frame_height <= 0:
        return grid[:, :, :3].flatten()

    for mv in motion_vectors:
        try:
            src_x = float(mv['src_x']) if isinstance(mv, dict) else float(mv.src_x)
            src_y = float(mv['src_y']) if isinstance(mv, dict) else float(mv.src_y)
            w = float(mv['w']) if isinstance(mv, dict) else float(mv.w)
            h = float(mv['h']) if isinstance(mv, dict) else float(mv.h)

            # FFmpeg MV: motion_x/motion_y 是子像素运动位移（单位：1/motion_scale 像素）
            motion_x = float(mv['motion_x']) if isinstance(mv, dict) else float(mv.motion_x)
            motion_y = float(mv['motion_y']) if isinstance(mv, dict) else float(mv.motion_y)
            motion_scale = float(mv['motion_scale']) if isinstance(mv, dict) else float(mv.motion_scale)
            if motion_scale == 0:
                motion_scale = 1.0

            # 实际像素位移
            dx = motion_x / motion_scale
            dy = motion_y / motion_scale
        except (AttributeError, KeyError, TypeError):
            continue

        # 速度归一化（抗分辨率 + 抗帧率）
        vel_x = (dx / frame_width) * fps
        vel_y = (dy / frame_height) * fps

        # 面积加权（抗 H.265 动态宏块切分）
        area_w = (w * h) / (frame_width * frame_height)

        # 定位网格
        gx = min(max(int(src_x / frame_width * grid_n), 0), grid_n - 1)
        gy = min(max(int(src_y / frame_height * grid_n), 0), grid_n - 1)

        # 加权累积
        grid[gy, gx, 0] += abs(vel_x) * area_w
        grid[gy, gx, 1] += abs(vel_y) * area_w
        grid[gy, gx, 2] += np.sqrt(vel_x**2 + vel_y**2) * area_w
        grid[gy, gx, 3] += area_w

    # 归一化为加权平均
    counts = grid[:, :, 3:4].clip(min=1e-8)
    return (grid[:, :, :3] / counts).flatten()  # 192d


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

    def project(self, feature: np.ndarray, output_bits: int,
                modality: str = "default") -> str:
        """将特征向量 LSH 投影到 output_bits 位，返回十六进制字符串。

        Args:
            feature: 输入特征向量
            output_bits: 输出比特数
            modality: 模态标识（vis/sem/tem），不同模态使用独立种子
                      防止相同维度的特征（如 vis 576d 和 sem 576d）
                      共享投影矩阵导致指纹混叠
        """
        input_dim = feature.shape[0]
        key = (input_dim, output_bits, modality)

        if key not in self._matrices:
            # 不同模态 → 不同种子 → 独立正交投影矩阵
            seed = _VIF_LSH_SEED + sum(ord(c) for c in modality)
            rng = np.random.RandomState(seed)
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
    [Legacy] 加权拼接三个特征向量，单一 LSH 降维到固定长度。

    已被 fuse_features_v2 取代，保留用于 fusion_legacy 模式和消融实验。
    缺陷：1248d concat 后全局投影，时序特征仅占 7.6% 被空间特征淹没。
    """
    weighted_phash = phash_feat * config.phash_weight
    weighted_semantic = semantic_feat * config.semantic_weight
    weighted_temporal = temporal_feat * config.temporal_weight
    fused = np.concatenate([weighted_phash, weighted_semantic, weighted_temporal])
    return _VIFLSHProjector.get_instance().project(fused, config.output_length)


def fuse_features_v2(
    phash_feat: np.ndarray,
    semantic_feat: np.ndarray,
    temporal_feat: np.ndarray,
    config: VIFConfig,
    temporal_tag: str = "f",
) -> str:
    """
    解耦 LSH：三模态独立投影，拼接为 256-bit 指纹 + 1 字符时序来源标记。

    输出格式：hash_vis(16hex) || hash_sem(16hex) || hash_tem(32hex) || temporal_tag(1char)
    总计 65 hex chars

    temporal_tag:
        'm' = MV 压缩域运动矢量
        'f' = Farneback 稠密光流
    """
    projector = _VIFLSHProjector.get_instance()
    hash_vis = projector.project(phash_feat, 64, modality="vis")
    hash_sem = projector.project(semantic_feat, 64, modality="sem")
    hash_tem = projector.project(temporal_feat, 128, modality="tem")
    return hash_vis + hash_sem + hash_tem + temporal_tag


def split_vif_hex(vif_hex: str):
    """
    将 VIF v2 hex 字符串拆分为三个模态哈希 + 时序来源标记。

    Returns:
        (hash_vis, hash_sem, hash_tem, temporal_tag)
        - 16hex=64bit, 16hex=64bit, 32hex=128bit, 1char ('m'/'f')
    """
    if not vif_hex or len(vif_hex) < 64:
        return None, None, None, None
    tag = vif_hex[64] if len(vif_hex) > 64 else 'f'  # 向后兼容旧格式
    return vif_hex[:16], vif_hex[16:32], vif_hex[32:64], tag


# ── 主入口 ────────────────────────────────────────────────────────────

def compute_vif(
    gop_frames: List[np.ndarray],
    config: Optional[VIFConfig] = None,
    motion_vectors: Optional[list] = None,
    frame_width: int = 0,
    frame_height: int = 0,
    fps: float = 30.0,
) -> Optional[str]:
    """
    计算多模态融合视频完整性指纹 (VIF)。

    Args:
        gop_frames: GOP 内多帧列表 (BGR numpy 数组)。
        config: VIF 配置
        motion_vectors: 压缩域运动矢量列表（有则用 MV，无则回退 Farneback）
        frame_width: 视频帧宽度（MV 归一化用）
        frame_height: 视频帧高度
        fps: 视频帧率

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
        feat = extract_phash_feature(keyframe)
        return _VIFLSHProjector.get_instance().project(feat, config.output_length)

    if config.mode == "semantic_only":
        feat = extract_semantic_feature(keyframe)
        return _VIFLSHProjector.get_instance().project(feat, config.output_length)

    if config.mode == "fusion":
        phash_feat = extract_phash_feature(keyframe)
        semantic_feat = extract_semantic_feature(keyframe)

        # 时序哈希始终用 Farneback（跨编码器一致性）
        # MV 仅作为存在性标记（'m'=有MV / 'f'=无MV），
        # 用于 TriStateVerifierV2 的 MV loss 惩罚检测 P/B 篡改
        temporal_feat = extract_temporal_feature(gop_frames)

        # MV 标记：有 MV 数据 → 'm'，无 → 'f'
        if motion_vectors and len(motion_vectors) > 0 and frame_width > 0:
            temporal_tag = 'm'
        else:
            temporal_tag = 'f'

        return fuse_features_v2(phash_feat, semantic_feat, temporal_feat, config,
                                temporal_tag=temporal_tag)

    if config.mode == "fusion_legacy":
        phash_feat = extract_phash_feature(keyframe)
        semantic_feat = extract_semantic_feature(keyframe)
        temporal_feat = extract_temporal_feature(gop_frames)
        return fuse_features(phash_feat, semantic_feat, temporal_feat, config)

    logger.warning("Unknown VIF_MODE=%s, returning None", config.mode)
    return None
