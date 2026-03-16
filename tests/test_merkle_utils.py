"""Tests for Merkle tree utilities."""
import pytest
import numpy as np
from services.merkle_utils import (
    build_merkle_root_and_proofs,
    apply_merkle_proof,
    sha256_digest,
    MerkleTree,
    compute_leaf_hash
)
from services.gop_splitter import GOPData


def test_sha256_digest():
    """Test SHA256 digest function."""
    data = b"test data"
    result = sha256_digest(data)
    assert len(result) == 32
    assert isinstance(result, bytes)


def test_build_merkle_root_single_leaf():
    """Test Merkle tree with single leaf."""
    leaf_hash = "a" * 64
    root, proofs = build_merkle_root_and_proofs([leaf_hash])
    assert root == leaf_hash
    assert len(proofs) == 1
    assert len(proofs[0]) == 0


def test_build_merkle_root_two_leaves():
    """Test Merkle tree with two leaves."""
    leaves = ["a" * 64, "b" * 64]
    root, proofs = build_merkle_root_and_proofs(leaves)
    assert len(proofs) == 2
    assert len(proofs[0]) == 1
    assert len(proofs[1]) == 1


def test_apply_merkle_proof():
    """Test Merkle proof verification."""
    leaves = ["a" * 64, "b" * 64]
    root, proofs = build_merkle_root_and_proofs(leaves)

    computed_root = apply_merkle_proof(leaves[0], proofs[0])
    assert computed_root == root


def test_merkle_proof_invalid():
    """Test Merkle proof with invalid leaf."""
    leaves = ["a" * 64, "b" * 64]
    root, proofs = build_merkle_root_and_proofs(leaves)

    wrong_leaf = "c" * 64
    computed_root = apply_merkle_proof(wrong_leaf, proofs[0])
    assert computed_root != root


# ── MerkleTree class tests ──────────────────────────────────────────


def _make_leaves(n):
    """Helper: generate n deterministic hex hash leaves."""
    import hashlib
    return [hashlib.sha256(f"leaf{i}".encode()).hexdigest() for i in range(n)]


def test_merkle_tree_single_leaf():
    """Single leaf: root == leaf, empty proof, verify passes."""
    leaves = _make_leaves(1)
    tree = MerkleTree(leaves)
    assert tree.root == leaves[0]
    proof = tree.get_proof(0)
    assert proof == []
    assert MerkleTree.verify_proof(leaves[0], proof, tree.root)


def test_merkle_tree_two_leaves():
    """Two leaves: simplest non-trivial tree, both proofs verify."""
    leaves = _make_leaves(2)
    tree = MerkleTree(leaves)
    assert len(tree.root) == 64
    for i in range(2):
        proof = tree.get_proof(i)
        assert len(proof) == 1
        assert MerkleTree.verify_proof(leaves[i], proof, tree.root)


def test_merkle_tree_four_leaves():
    """Four leaves (power of 2): all proofs verify, no padding needed."""
    leaves = _make_leaves(4)
    tree = MerkleTree(leaves)
    for i in range(4):
        proof = tree.get_proof(i)
        assert MerkleTree.verify_proof(leaves[i], proof, tree.root)


def test_merkle_tree_five_leaves_padding():
    """Five leaves (non-power-of-2): padding to 8, all original proofs verify."""
    leaves = _make_leaves(5)
    tree = MerkleTree(leaves)
    # Padded to 8 leaves
    assert len(tree._levels[0]) == 8
    for i in range(5):
        proof = tree.get_proof(i)
        assert MerkleTree.verify_proof(leaves[i], proof, tree.root)


def test_merkle_tree_tampered_leaf():
    """Tampered leaf hash fails proof verification."""
    import hashlib
    leaves = _make_leaves(4)
    tree = MerkleTree(leaves)
    proof = tree.get_proof(0)
    tampered = hashlib.sha256(b"tampered").hexdigest()
    assert not MerkleTree.verify_proof(tampered, proof, tree.root)


def test_merkle_tree_json_roundtrip():
    """to_json -> from_json preserves root and all proofs."""
    leaves = _make_leaves(6)
    tree = MerkleTree(leaves)
    json_str = tree.to_json()
    restored = MerkleTree.from_json(json_str)
    assert restored.root == tree.root
    for i in range(len(leaves)):
        assert restored.get_proof(i) == tree.get_proof(i)
        assert MerkleTree.verify_proof(leaves[i], restored.get_proof(i), restored.root)


# ── compute_leaf_hash tests ──────────────────────────────────────────


def test_compute_leaf_hash_all_fields():
    """Test compute_leaf_hash with all fields provided."""
    sha256 = "a" * 64
    phash = "b" * 16
    semantic = "c" * 64

    result = compute_leaf_hash(sha256, phash, semantic)

    assert isinstance(result, str)
    assert len(result) == 64  # SHA-256 hex
    # Should be deterministic
    result2 = compute_leaf_hash(sha256, phash, semantic)
    assert result == result2


def test_compute_leaf_hash_missing_phash():
    """Test compute_leaf_hash with missing phash (uses placeholder)."""
    sha256 = "a" * 64
    semantic = "c" * 64

    result = compute_leaf_hash(sha256, None, semantic)

    assert isinstance(result, str)
    assert len(result) == 64
    # Should use "0" * 16 placeholder for phash
    expected = compute_leaf_hash(sha256, "0" * 16, semantic)
    assert result == expected


def test_compute_leaf_hash_missing_semantic():
    """Test compute_leaf_hash with missing semantic_hash (uses placeholder)."""
    sha256 = "a" * 64
    phash = "b" * 16

    result = compute_leaf_hash(sha256, phash, None)

    assert isinstance(result, str)
    assert len(result) == 64
    # Should use "0" * 64 placeholder for semantic
    expected = compute_leaf_hash(sha256, phash, "0" * 64)
    assert result == expected


def test_compute_leaf_hash_all_missing():
    """Test compute_leaf_hash with all optional fields missing."""
    sha256 = "a" * 64

    result = compute_leaf_hash(sha256, None, None)

    assert isinstance(result, str)
    assert len(result) == 64
    # Should use placeholders for both
    expected = compute_leaf_hash(sha256, "0" * 16, "0" * 64)
    assert result == expected


def test_compute_leaf_hash_deterministic():
    """Test that compute_leaf_hash is deterministic."""
    sha256 = "abc123" + "0" * 58
    phash = "def456" + "0" * 10
    semantic = "789ghi" + "0" * 58

    result1 = compute_leaf_hash(sha256, phash, semantic)
    result2 = compute_leaf_hash(sha256, phash, semantic)
    result3 = compute_leaf_hash(sha256, phash, semantic)

    assert result1 == result2 == result3


def test_compute_leaf_hash_different_inputs():
    """Test that different inputs produce different hashes."""
    sha256_1 = "a" * 64
    sha256_2 = "b" * 64
    phash = "c" * 16
    semantic = "d" * 64

    result1 = compute_leaf_hash(sha256_1, phash, semantic)
    result2 = compute_leaf_hash(sha256_2, phash, semantic)

    assert result1 != result2


# ── build_merkle_root_and_proofs with GOPData ──────────────────────


def test_build_merkle_with_gopdata():
    """Test build_merkle_root_and_proofs accepts GOPData objects."""
    # Create mock GOPData objects
    gops = []
    for i in range(3):
        gop = GOPData(
            gop_id=i,
            raw_bytes=b"test",
            sha256_hash=f"{i}" * 64,
            start_time=float(i),
            end_time=float(i + 1),
            frame_count=10,
            byte_size=100,
            keyframe_frame=np.zeros((480, 640, 3), dtype=np.uint8),
            phash=f"{i}" * 16,
            semantic_hash=f"{i}" * 64
        )
        gops.append(gop)

    root, proofs = build_merkle_root_and_proofs(gops)

    assert isinstance(root, str)
    assert len(root) == 64
    assert len(proofs) == 3
    # Each proof should be a list
    for proof in proofs:
        assert isinstance(proof, list)


def test_build_merkle_with_gopdata_missing_semantic():
    """Test build_merkle_root_and_proofs with GOPData missing semantic_hash."""
    gops = []
    for i in range(2):
        gop = GOPData(
            gop_id=i,
            raw_bytes=b"test",
            sha256_hash=f"{i}" * 64,
            start_time=float(i),
            end_time=float(i + 1),
            frame_count=10,
            byte_size=100,
            keyframe_frame=np.zeros((480, 640, 3), dtype=np.uint8),
            phash=f"{i}" * 16,
            semantic_hash=None  # Missing semantic
        )
        gops.append(gop)

    root, proofs = build_merkle_root_and_proofs(gops)

    assert isinstance(root, str)
    assert len(root) == 64
    assert len(proofs) == 2


def test_build_merkle_backward_compatible():
    """Test build_merkle_root_and_proofs still works with string list."""
    leaves = ["a" * 64, "b" * 64, "c" * 64]
    root, proofs = build_merkle_root_and_proofs(leaves)

    assert isinstance(root, str)
    assert len(root) == 64
    assert len(proofs) == 3

