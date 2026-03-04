"""Merkle Tree construction and proof verification utilities."""
import hashlib
from typing import Dict, List, Tuple


def sha256_digest(data: bytes) -> bytes:
    """Compute SHA256 digest of data."""
    return hashlib.sha256(data).digest()


def build_merkle_root_and_proofs(leaf_hashes: List[str]) -> Tuple[str, List[List[Dict[str, str]]]]:
    """
    Build Merkle tree from leaf hashes and generate proofs for each leaf.

    Returns:
        (merkle_root_hex, proofs) where proofs[i] is the proof for leaf i
    """
    if not leaf_hashes:
        raise ValueError("leaf_hashes cannot be empty")

    levels: List[List[bytes]] = [[bytes.fromhex(h) for h in leaf_hashes]]

    while len(levels[-1]) > 1:
        current = levels[-1]
        nxt: List[bytes] = []
        for i in range(0, len(current), 2):
            left = current[i]
            right = current[i + 1] if i + 1 < len(current) else current[i]
            nxt.append(sha256_digest(left + right))
        levels.append(nxt)

    root = levels[-1][0].hex()

    proofs: List[List[Dict[str, str]]] = []
    for leaf_idx in range(len(leaf_hashes)):
        idx = leaf_idx
        proof: List[Dict[str, str]] = []
        for level in levels[:-1]:
            if idx % 2 == 0:
                sibling_idx = idx + 1 if idx + 1 < len(level) else idx
                position = "right"
            else:
                sibling_idx = idx - 1
                position = "left"
            proof.append({"position": position, "hash": level[sibling_idx].hex()})
            idx //= 2
        proofs.append(proof)

    return root, proofs


def apply_merkle_proof(leaf_hash: str, proof: List[Dict[str, str]]) -> str:
    """
    Apply Merkle proof to compute root hash from leaf.

    Args:
        leaf_hash: Hex string of leaf hash
        proof: List of proof nodes with 'position' and 'hash'

    Returns:
        Computed root hash as hex string
    """
    current = bytes.fromhex(leaf_hash)
    for node in proof:
        sibling = bytes.fromhex(node["hash"])
        if node["position"] == "left":
            current = sha256_digest(sibling + current)
        else:
            current = sha256_digest(current + sibling)
    return current.hex()
