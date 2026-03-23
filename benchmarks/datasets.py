"""
合成测试数据集管理。

生成不同分辨率的合成视频帧和 GOP 数据，无需真实视频文件。
"""

import hashlib
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class SyntheticGOP:
    """合成 GOP 数据。"""
    gop_id: int
    frames: List[np.ndarray]
    sha256_hash: str
    resolution: Tuple[int, int]
    frame_count: int

    @property
    def keyframe(self) -> np.ndarray:
        return self.frames[0]


def generate_frame(
    width: int, height: int, seed: Optional[int] = None
) -> np.ndarray:
    """生成一帧合成图像 (H, W, 3) uint8。"""
    rng = np.random.RandomState(seed)
    return rng.randint(0, 256, (height, width, 3), dtype=np.uint8)


def generate_gop(
    gop_id: int,
    width: int,
    height: int,
    num_frames: int = 15,
    seed: Optional[int] = None,
) -> SyntheticGOP:
    """生成一个合成 GOP。"""
    base_seed = seed if seed is not None else gop_id * 1000
    frames = []
    for i in range(num_frames):
        frame = generate_frame(width, height, seed=base_seed + i)
        frames.append(frame)

    # 计算 SHA-256（模拟原始字节哈希）
    raw_bytes = b"".join(f.tobytes()[:1024] for f in frames)
    sha256_hash = hashlib.sha256(raw_bytes).hexdigest()

    return SyntheticGOP(
        gop_id=gop_id,
        frames=frames,
        sha256_hash=sha256_hash,
        resolution=(width, height),
        frame_count=num_frames,
    )


def generate_dataset(
    num_gops: int,
    width: int,
    height: int,
    num_frames: int = 15,
) -> List[SyntheticGOP]:
    """生成一组 GOP 数据。"""
    return [
        generate_gop(i, width, height, num_frames, seed=i * 1000)
        for i in range(num_gops)
    ]


def apply_tamper(
    frame: np.ndarray,
    tamper_type: str,
    intensity: float = 0.5,
    seed: int = 42,
) -> np.ndarray:
    """
    对帧施加篡改。

    Args:
        frame: 原始帧 (H, W, 3)
        tamper_type: 篡改类型
        intensity: 篡改强度 [0, 1]
        seed: 随机种子

    Returns:
        篡改后的帧
    """
    rng = np.random.RandomState(seed)
    h, w = frame.shape[:2]
    result = frame.copy()

    if tamper_type == "frame_replace":
        # 替换部分区域
        region_h = int(h * intensity)
        region_w = int(w * intensity)
        y, x = rng.randint(0, max(1, h - region_h)), rng.randint(0, max(1, w - region_w))
        result[y:y+region_h, x:x+region_w] = rng.randint(0, 256, (region_h, region_w, 3), dtype=np.uint8)

    elif tamper_type == "content_overlay":
        # 叠加内容
        overlay = rng.randint(0, 256, frame.shape, dtype=np.uint8)
        alpha = intensity * 0.5
        result = np.clip(frame * (1 - alpha) + overlay * alpha, 0, 255).astype(np.uint8)

    elif tamper_type == "temporal_shift":
        # 时间偏移（行移动模拟）
        shift = int(h * intensity * 0.3)
        result = np.roll(frame, shift, axis=0)

    elif tamper_type == "compression":
        # 压缩伪影（量化模拟）
        block_size = max(2, int(8 * intensity))
        for y_b in range(0, h, block_size):
            for x_b in range(0, w, block_size):
                block = result[y_b:y_b+block_size, x_b:x_b+block_size]
                result[y_b:y_b+block_size, x_b:x_b+block_size] = np.mean(block, axis=(0, 1), keepdims=True).astype(np.uint8)

    elif tamper_type == "noise_inject":
        # 噪声注入
        noise = rng.normal(0, intensity * 50, frame.shape)
        result = np.clip(frame.astype(float) + noise, 0, 255).astype(np.uint8)

    return result
