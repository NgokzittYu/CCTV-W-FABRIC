"""Tests for Merkle tree utilities."""
import pytest
from services.merkle_utils import build_merkle_root_and_proofs, apply_merkle_proof, sha256_digest


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
