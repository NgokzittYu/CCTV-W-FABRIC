"""
Baseline: 扁平 Merkle 树。

不使用三级层次结构，所有 GOP 哈希直接构建一棵扁平 Merkle 树。
"""

import hashlib
from typing import List, Tuple


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def build_flat_merkle(leaf_hashes: List[str]) -> Tuple[str, List[List[str]]]:
    """
    构建扁平 Merkle 树。

    Returns:
        (root_hash, tree_levels)
    """
    if not leaf_hashes:
        return "", []

    current_level = list(leaf_hashes)
    levels = [current_level[:]]

    while len(current_level) > 1:
        next_level = []
        for i in range(0, len(current_level), 2):
            left = current_level[i]
            right = current_level[i + 1] if i + 1 < len(current_level) else left
            parent = _sha256(left + right)
            next_level.append(parent)
        current_level = next_level
        levels.append(current_level[:])

    return current_level[0], levels


def get_proof_length(num_leaves: int) -> int:
    """扁平树的证明路径长度 = ceil(log2(n))。"""
    import math
    return math.ceil(math.log2(max(1, num_leaves)))
