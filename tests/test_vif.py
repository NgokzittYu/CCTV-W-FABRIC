"""
VIF（多模态融合视频完整性指纹 -> GOP级轻量视觉宽容指纹 V4）单元测试

测试内容：
- 特征提取（CNN）
- 输出格式与长度一致性 (256-bit)
- 稳定性（同一输入多次计算结果一致）
- 区分度（不同输入指纹汉明距离 > 0）
- Merkle Tree 兼容性
"""

import os
from unittest import mock

import numpy as np
import pytest

from services.vif import (
    VIFConfig,
    compute_vif,
    extract_phash_feature,
    _PHASH_FEAT_DIM,
)


# ── 辅助函数 ──────────────────────────────────────────────────────────

def _make_frame(seed: int = 42, h: int = 120, w: int = 160) -> np.ndarray:
    """生成确定性合成 BGR 帧。"""
    rng = np.random.RandomState(seed)
    return rng.randint(0, 256, (h, w, 3), dtype=np.uint8)


def _make_gop_frames(seed: int = 42, n: int = 5) -> list:
    """生成 GOP 多帧列表。"""
    return [_make_frame(seed=seed + i) for i in range(n)]


def _hamming_hex(hex1: str, hex2: str) -> int:
    """计算两个十六进制字符串的汉明距离（比特级）。"""
    val1 = int(hex1, 16)
    val2 = int(hex2, 16)
    return (val1 ^ val2).bit_count()


# ── VIFConfig ─────────────────────────────────────────────────────────

class TestVIFConfig:
    def test_default_output_length(self):
        config = VIFConfig()
        assert config.output_length == 256


# ── 特征提取 ──────────────────────────────────────────────────────────

class TestPhashFeature:
    def test_output_shape(self):
        frame = _make_frame()
        feat = extract_phash_feature(frame)
        assert feat.shape == (_PHASH_FEAT_DIM,)
        assert feat.dtype == np.float64

    def test_deterministic(self):
        frame = _make_frame(seed=1)
        f1 = extract_phash_feature(frame)
        f2 = extract_phash_feature(frame.copy())
        np.testing.assert_array_equal(f1, f2)

    def test_invalid_input_returns_zero(self):
        feat = extract_phash_feature(np.array([]))
        assert feat.shape == (_PHASH_FEAT_DIM,)
        assert np.all(feat == 0)


# ── compute_vif 行为 ──────────────────────────────────────────────────

class TestComputeVIF:
    def test_off_mode_returns_none(self):
        config = VIFConfig(mode="off")
        result = compute_vif(_make_gop_frames(), config)
        assert result is None

    def test_fusion_format(self):
        config = VIFConfig()
        result = compute_vif(_make_gop_frames(n=3), config)
        assert result is not None
        hex_len = config.output_length // 4
        assert len(result) == hex_len
        assert all(c in "0123456789abcdef" for c in result)

    def test_empty_frames_returns_none(self):
        config = VIFConfig()
        result = compute_vif([], config)
        assert result is None


# ── 稳定性 ────────────────────────────────────────────────────────────

class TestVIFStability:
    def test_same_input_same_output(self):
        """相同输入多次计算应得到完全相同的 VIF。"""
        config = VIFConfig()
        frames1 = _make_gop_frames(seed=100, n=2)
        frames2 = _make_gop_frames(seed=100, n=2)

        r1 = compute_vif(frames1, config)
        r2 = compute_vif(frames2, config)

        assert r1 == r2


# ── 区分度 ────────────────────────────────────────────────────────────

class TestVIFDiscrimination:
    def test_different_input_different_output(self):
        """不同输入的 VIF 汉明距离应 > 0。"""
        config = VIFConfig()
        frames_a = _make_gop_frames(seed=1, n=2)
        frames_b = _make_gop_frames(seed=999, n=2)

        vif_a = compute_vif(frames_a, config)
        vif_b = compute_vif(frames_b, config)

        assert vif_a != vif_b
        distance = _hamming_hex(vif_a, vif_b)
        assert distance > 0, f"Hamming distance too small: {distance}"


# ── Merkle Tree 兼容性 ────────────────────────────────────────────────

class TestVIFMerkleCompatibility:
    def test_vif_as_leaf_hash_component(self):
        """VIF 字符串可正确用于 compute_leaf_hash。"""
        from services.merkle_utils import compute_leaf_hash

        sha256 = "a" * 64
        config = VIFConfig()
        vif = compute_vif(_make_gop_frames(n=2), config)

        # 使用 VIF 计算叶子哈希
        leaf1 = compute_leaf_hash(sha256, vif=vif)
        leaf2 = compute_leaf_hash(sha256, vif=vif)

        assert leaf1 == leaf2  # 确定性
        assert len(leaf1) == 64  # SHA-256 hex

    def test_merkle_tree_with_vif_leaves(self):
        """VIF 叶子可正确构建 Merkle Tree。"""
        from services.merkle_utils import MerkleTree, compute_leaf_hash

        config = VIFConfig()
        leaves = []
        for seed in range(4):
            sha256 = f"{seed:064x}"
            vif = compute_vif(_make_gop_frames(seed=seed * 10, n=2), config)
            leaf = compute_leaf_hash(sha256, vif=vif)
            leaves.append(leaf)

        tree = MerkleTree(leaves)
        assert tree.root is not None
        assert len(tree.root) == 64

        # 验证 proof
        for i in range(4):
            proof = tree.get_proof(i)
            assert MerkleTree.verify_proof(leaves[i], proof, tree.root)
