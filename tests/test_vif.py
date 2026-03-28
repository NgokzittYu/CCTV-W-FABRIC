"""
VIF（多模态融合视频完整性指纹）单元测试

测试内容：
- 各模式（off / phash_only / semantic_only / fusion）输出格式
- 输出长度一致性
- 稳定性（同一输入多次计算结果一致）
- 区分度（不同输入指纹汉明距离 > 阈值）
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
    extract_semantic_feature,
    extract_temporal_feature,
    _PHASH_FEAT_DIM,
    _SEMANTIC_FEAT_DIM,
    _TEMPORAL_FEAT_DIM,
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
    def test_default_mode_off(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            os.environ.pop("VIF_MODE", None)
            config = VIFConfig()
            assert config.mode == "off"

    def test_mode_from_env(self):
        with mock.patch.dict(os.environ, {"VIF_MODE": "fusion"}):
            config = VIFConfig()
            assert config.mode == "fusion"

    def test_weight_from_env(self):
        with mock.patch.dict(os.environ, {
            "VIF_MODE": "fusion",
            "VIF_PHASH_WEIGHT": "0.5",
            "VIF_SEMANTIC_WEIGHT": "0.3",
            "VIF_TEMPORAL_WEIGHT": "0.2",
        }):
            config = VIFConfig()
            assert config.phash_weight == 0.5
            assert config.semantic_weight == 0.3
            assert config.temporal_weight == 0.2

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


class TestSemanticFeature:
    def test_output_shape(self):
        frame = _make_frame()
        feat = extract_semantic_feature(frame)
        assert feat.shape == (_SEMANTIC_FEAT_DIM,)
        assert feat.dtype == np.float64

    def test_l2_normalized(self):
        frame = _make_frame()
        feat = extract_semantic_feature(frame)
        norm = np.linalg.norm(feat)
        # 应该被归一化到 1（或为零向量）
        if norm > 0:
            assert abs(norm - 1.0) < 1e-6

    def test_deterministic(self):
        frame = _make_frame(seed=10)
        f1 = extract_semantic_feature(frame)
        f2 = extract_semantic_feature(frame.copy())
        np.testing.assert_array_almost_equal(f1, f2)

    def test_invalid_input_returns_zero(self):
        feat = extract_semantic_feature(None)
        assert feat.shape == (_SEMANTIC_FEAT_DIM,)
        assert np.all(feat == 0)


class TestTemporalFeature:
    def test_output_shape(self):
        frames = _make_gop_frames(n=5)
        feat = extract_temporal_feature(frames)
        assert feat.shape == (_TEMPORAL_FEAT_DIM,)

    def test_single_frame_returns_zero(self):
        """单帧输入应优雅退化为零向量。"""
        feat = extract_temporal_feature([_make_frame()])
        assert feat.shape == (_TEMPORAL_FEAT_DIM,)
        assert np.all(feat == 0)

    def test_none_returns_zero(self):
        feat = extract_temporal_feature(None)
        assert feat.shape == (_TEMPORAL_FEAT_DIM,)
        assert np.all(feat == 0)

    def test_non_zero_with_multiple_frames(self):
        """多帧输入应产生非零光流特征。"""
        frames = _make_gop_frames(seed=1, n=4)
        feat = extract_temporal_feature(frames)
        assert not np.all(feat == 0), "temporal feature should be non-zero for different frames"

    def test_deterministic(self):
        frames1 = _make_gop_frames(seed=42, n=3)
        frames2 = _make_gop_frames(seed=42, n=3)
        f1 = extract_temporal_feature(frames1)
        f2 = extract_temporal_feature(frames2)
        np.testing.assert_array_almost_equal(f1, f2)


# ── compute_vif 各模式 ────────────────────────────────────────────────

class TestComputeVIF:
    def test_off_mode_returns_none(self):
        config = VIFConfig(mode="off")
        result = compute_vif(_make_gop_frames(), config)
        assert result is None

    def test_phash_only_format(self):
        config = VIFConfig(mode="phash_only")
        result = compute_vif(_make_gop_frames(), config)
        assert result is not None
        assert isinstance(result, str)
        hex_len = config.output_length // 4  # 64
        assert len(result) == hex_len
        assert all(c in "0123456789abcdef" for c in result)

    def test_semantic_only_format(self):
        config = VIFConfig(mode="semantic_only")
        result = compute_vif(_make_gop_frames(), config)
        assert result is not None
        hex_len = config.output_length // 4
        assert len(result) == hex_len
        assert all(c in "0123456789abcdef" for c in result)

    def test_fusion_format(self):
        config = VIFConfig(mode="fusion")
        result = compute_vif(_make_gop_frames(n=5), config)
        assert result is not None
        hex_len = config.output_length // 4
        assert len(result) == hex_len
        assert all(c in "0123456789abcdef" for c in result)

    def test_unknown_mode_returns_none(self):
        config = VIFConfig(mode="invalid_mode")
        result = compute_vif(_make_gop_frames(), config)
        assert result is None

    def test_empty_frames_returns_none(self):
        config = VIFConfig(mode="fusion")
        result = compute_vif([], config)
        assert result is None


# ── 稳定性 ────────────────────────────────────────────────────────────

class TestVIFStability:
    @pytest.mark.parametrize("mode", ["phash_only", "semantic_only", "fusion"])
    def test_same_input_same_output(self, mode):
        """相同输入多次计算应得到完全相同的 VIF。"""
        config = VIFConfig(mode=mode)
        frames1 = _make_gop_frames(seed=100, n=4)
        frames2 = _make_gop_frames(seed=100, n=4)
        frames3 = _make_gop_frames(seed=100, n=4)

        r1 = compute_vif(frames1, config)
        r2 = compute_vif(frames2, config)
        r3 = compute_vif(frames3, config)

        assert r1 == r2 == r3


# ── 区分度 ────────────────────────────────────────────────────────────

class TestVIFDiscrimination:
    @pytest.mark.parametrize("mode", ["phash_only", "semantic_only", "fusion"])
    def test_different_input_different_output(self, mode):
        """不同输入的 VIF 汉明距离应 > 0。"""
        config = VIFConfig(mode=mode)
        frames_a = _make_gop_frames(seed=1, n=4)
        frames_b = _make_gop_frames(seed=999, n=4)

        vif_a = compute_vif(frames_a, config)
        vif_b = compute_vif(frames_b, config)

        assert vif_a != vif_b
        distance = _hamming_hex(vif_a, vif_b)
        # 不同内容应有显著汉明距离
        assert distance > 5, f"Hamming distance too small: {distance}"


# ── Merkle Tree 兼容性 ────────────────────────────────────────────────

class TestVIFMerkleCompatibility:
    def test_vif_as_leaf_hash_component(self):
        """VIF 字符串可正确用于 compute_leaf_hash。"""
        from services.merkle_utils import compute_leaf_hash

        sha256 = "a" * 64
        config = VIFConfig(mode="fusion")
        vif = compute_vif(_make_gop_frames(n=3), config)

        # 使用 VIF 计算叶子哈希
        leaf1 = compute_leaf_hash(sha256, vif=vif)
        leaf2 = compute_leaf_hash(sha256, vif=vif)

        assert leaf1 == leaf2  # 确定性
        assert len(leaf1) == 64  # SHA-256 hex

    def test_vif_leaf_differs_from_legacy(self):
        """VIF 模式的叶子哈希应与传统模式不同。"""
        from services.merkle_utils import compute_leaf_hash

        sha256 = "b" * 64
        phash = "c" * 16
        semantic = "d" * 64

        legacy_leaf = compute_leaf_hash(sha256, phash, semantic)

        config = VIFConfig(mode="fusion")
        vif = compute_vif(_make_gop_frames(n=3), config)
        vif_leaf = compute_leaf_hash(sha256, vif=vif)

        assert legacy_leaf != vif_leaf

    def test_merkle_tree_with_vif_leaves(self):
        """VIF 叶子可正确构建 Merkle Tree。"""
        from services.merkle_utils import MerkleTree, compute_leaf_hash

        config = VIFConfig(mode="fusion")
        leaves = []
        for seed in range(4):
            sha256 = f"{seed:064x}"
            vif = compute_vif(_make_gop_frames(seed=seed * 10, n=3), config)
            leaf = compute_leaf_hash(sha256, vif=vif)
            leaves.append(leaf)

        tree = MerkleTree(leaves)
        assert tree.root is not None
        assert len(tree.root) == 64

        # 验证 proof
        for i in range(4):
            proof = tree.get_proof(i)
            assert MerkleTree.verify_proof(leaves[i], proof, tree.root)

    def test_backward_compatibility_no_vif(self):
        """VIF=None 时 compute_leaf_hash 行为与原来一致。"""
        from services.merkle_utils import compute_leaf_hash

        sha256 = "e" * 64
        phash = "f" * 16
        semantic = "1" * 64

        result_with_none = compute_leaf_hash(sha256, phash, semantic, vif=None)
        result_without_arg = compute_leaf_hash(sha256, phash, semantic)

        assert result_with_none == result_without_arg
