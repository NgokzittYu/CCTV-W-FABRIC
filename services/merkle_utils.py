"""Merkle Tree construction and proof verification utilities."""
import hashlib
import json
from typing import Dict, List, Tuple, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from services.gop_splitter import GOPData


def sha256_digest(data: bytes) -> bytes:
    """Compute SHA256 digest of data."""
    return hashlib.sha256(data).digest()


def compute_leaf_hash(
    sha256_hash: str,
    phash: Optional[str] = None,
    semantic_hash: Optional[str] = None
) -> str:
    """
    计算组合 Merkle 叶子哈希。

    组合三个哈希：SHA-256（字节完整性）+ pHash（视觉相似性）+
    semantic_hash（内容语义）为单个叶子哈希。

    使用固定占位符处理 None 值，确保叶子结构一致性：
    - phash 缺失 → 用 "0" * 16（64-bit pHash）
    - semantic_hash 缺失 → 用 "0" * 64（256-bit SHA-256）

    这保证了相同 GOP 始终产生相同的叶子哈希，无论语义提取是否成功。

    Args:
        sha256_hash: GOP 原始字节 SHA-256（必需）
        phash: 感知哈希（可选，16 字符十六进制）
        semantic_hash: 语义指纹哈希（可选，64 字符十六进制）

    Returns:
        SHA-256(sha256 + phash + semantic) 的十六进制字符串
    """
    # 使用占位符处理 None 值，保持结构一致
    phash_str = phash if phash else "0" * 16
    semantic_str = semantic_hash if semantic_hash else "0" * 64

    # 拼接三个哈希
    combined = sha256_hash + phash_str + semantic_str

    # 对拼接字符串计算哈希
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()


def build_merkle_root_and_proofs(
    leaves: Union[List[str], List["GOPData"]]
) -> Tuple[str, List[List[Dict[str, str]]]]:
    """
    Build Merkle tree from leaf hashes and generate proofs for each leaf.

    Args:
        leaves: Either a list of hash strings (backward compatible) or a list of GOPData objects

    Returns:
        (merkle_root_hex, proofs) where proofs[i] is the proof for leaf i
    """
    # Handle input type
    if not leaves:
        raise ValueError("leaves cannot be empty")

    # Check if we have GOPData objects or strings
    if hasattr(leaves[0], 'sha256_hash'):
        # GOPData objects - compute composite leaf hashes
        leaf_hashes = [
            compute_leaf_hash(
                gop.sha256_hash,
                gop.phash,
                gop.semantic_hash
            )
            for gop in leaves
        ]
    else:
        # String hashes - use directly (backward compatible)
        leaf_hashes = leaves

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

    def __init__(self, leaves: Union[List[str], List["GOPData"]]) -> None:
        if not leaves:
            raise ValueError("leaves cannot be empty")

        # Convert GOPData to leaf hashes if needed
        if hasattr(leaves[0], 'sha256_hash'):
            # GOPData objects - compute composite leaf hashes
            leaf_hashes = [
                compute_leaf_hash(
                    gop.sha256_hash,
                    gop.phash,
                    gop.semantic_hash
                )
                for gop in leaves
            ]
        else:
            # String hashes - use directly
            leaf_hashes = leaves

        self._original_leaves: List[str] = list(leaf_hashes)

        # Pad to next power of 2
        if len(leaf_hashes) == 1:
            n = 1
        else:
            n = 1 << (len(leaf_hashes) - 1).bit_length()
        padded = list(leaf_hashes) + [leaf_hashes[-1]] * (n - len(leaf_hashes))

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
