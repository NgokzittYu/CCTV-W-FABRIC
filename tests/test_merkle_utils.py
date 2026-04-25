import pytest

from services.merkle_utils import (
    MerkleTree,
    apply_merkle_proof,
    build_merkle_root_and_proofs,
    compute_leaf_hash,
)


pytestmark = pytest.mark.unit


def test_leaf_hash_is_deterministic_and_uses_vif(hash_hex):
    sha = hash_hex("gop-1")
    vif = "a" * 64

    first = compute_leaf_hash(sha, phash="b" * 16, semantic_hash="c" * 64, vif=vif)
    second = compute_leaf_hash(sha, phash="different", semantic_hash="different", vif=vif)

    assert first == second
    assert len(first) == 64


def test_merkle_proofs_rebuild_root(hash_hex):
    leaves = [hash_hex(f"leaf-{i}") for i in range(5)]

    root, proofs = build_merkle_root_and_proofs(leaves)

    assert len(root) == 64
    assert len(proofs) == len(leaves)
    for leaf, proof in zip(leaves, proofs):
        assert apply_merkle_proof(leaf, proof) == root


def test_tampered_leaf_does_not_match_root(hash_hex):
    leaves = [hash_hex(f"leaf-{i}") for i in range(4)]
    root, proofs = build_merkle_root_and_proofs(leaves)
    tampered_leaf = hash_hex("tampered")

    assert apply_merkle_proof(tampered_leaf, proofs[0]) != root


def test_merkle_tree_json_roundtrip(hash_hex):
    leaves = [hash_hex("a"), hash_hex("b"), hash_hex("c")]
    tree = MerkleTree(leaves)

    restored = MerkleTree.from_json(tree.to_json())

    assert restored.root == tree.root
    assert restored.get_proof(1) == tree.get_proof(1)


def test_empty_leaf_list_is_rejected():
    with pytest.raises(ValueError, match="leaves cannot be empty"):
        build_merkle_root_and_proofs([])
