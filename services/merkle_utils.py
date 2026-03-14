"""Merkle Tree construction and proof verification utilities."""
import hashlib
import json
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


class MerkleTree:
    """Full Merkle tree with proof generation, verification, and JSON serialization.

    Leaves are padded to the next power of 2 by duplicating the last leaf.
    Proof format uses the same convention as apply_merkle_proof:
    position indicates where the sibling sits ("left" or "right").
    """

    def __init__(self, leaves: List[str]) -> None:
        if not leaves:
            raise ValueError("leaves cannot be empty")

        self._original_leaves: List[str] = list(leaves)

        # Pad to next power of 2
        if len(leaves) == 1:
            n = 1
        else:
            n = 1 << (len(leaves) - 1).bit_length()
        padded = list(leaves) + [leaves[-1]] * (n - len(leaves))

        # Build tree bottom-up, all hex strings
        self._levels: List[List[str]] = [padded]
        while len(self._levels[-1]) > 1:
            prev = self._levels[-1]
            nxt: List[str] = []
            for i in range(0, len(prev), 2):
                combined = bytes.fromhex(prev[i]) + bytes.fromhex(prev[i + 1])
                nxt.append(sha256_digest(combined).hex())
            self._levels.append(nxt)

        self.root: str = self._levels[-1][0]

    def get_proof(self, leaf_index: int) -> List[Dict[str, str]]:
        """Generate Merkle proof for the given original leaf index."""
        if not (0 <= leaf_index < len(self._original_leaves)):
            raise IndexError(f"leaf_index {leaf_index} out of range [0, {len(self._original_leaves)})")

        proof: List[Dict[str, str]] = []
        idx = leaf_index
        for level in self._levels[:-1]:
            sibling_idx = idx ^ 1
            if idx % 2 == 0:
                position = "right"
            else:
                position = "left"
            proof.append({"hash": level[sibling_idx], "position": position})
            idx //= 2
        return proof

    @staticmethod
    def verify_proof(leaf_hash: str, proof: List[Dict[str, str]], root: str) -> bool:
        """Verify a Merkle proof against a known root. Same semantics as apply_merkle_proof."""
        current = bytes.fromhex(leaf_hash)
        for node in proof:
            sibling = bytes.fromhex(node["hash"])
            if node["position"] == "left":
                current = sha256_digest(sibling + current)
            else:
                current = sha256_digest(current + sibling)
        return current.hex() == root

    def to_json(self) -> str:
        """Serialize the full tree structure to JSON."""
        return json.dumps({
            "original_leaves": self._original_leaves,
            "levels": self._levels,
            "root": self.root,
        })

    @classmethod
    def from_json(cls, json_str: str) -> "MerkleTree":
        """Deserialize a MerkleTree from JSON without rebuilding."""
        data = json.loads(json_str)
        obj = cls.__new__(cls)
        obj._original_leaves = data["original_leaves"]
        obj._levels = data["levels"]
        obj.root = data["root"]
        return obj
