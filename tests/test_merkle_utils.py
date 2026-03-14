"""Tests for Merkle tree utilities."""
import pytest
from services.merkle_utils import build_merkle_root_and_proofs, apply_merkle_proof, sha256_digest, MerkleTree


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
