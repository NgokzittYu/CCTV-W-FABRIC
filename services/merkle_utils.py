"""Merkle Tree construction and proof verification utilities."""
import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from services.gop_splitter import GOPData


def sha256_digest(data: bytes) -> bytes:
    """Compute SHA256 digest of data."""
    return hashlib.sha256(data).digest()


def compute_leaf_hash(
    sha256_hash: str,
    phash: Optional[str] = None,
    semantic_hash: Optional[str] = None,
    vif: Optional[str] = None,
) -> str:
    """
    计算组合 Merkle 叶子哈希。

    当 vif 不为 None 时，使用 VIF 替代 phash + semantic_hash 作为感知标识组件。
    当 vif 为 None 时，行为与原来完全一致（向后兼容）。

    Args:
        sha256_hash: GOP 原始字节 SHA-256（必需）
        phash: 感知哈希（可选，16 字符十六进制）
        semantic_hash: 语义指纹哈希（可选，64 字符十六进制）
        vif: 多模态融合指纹（可选，固定长度十六进制）

    Returns:
        SHA-256 的十六进制字符串
    """
    if vif is not None:
        # VIF 模式：sha256 + vif
        combined = sha256_hash + vif
    else:
        # 传统模式：sha256 + phash + semantic_hash
        phash_str = phash if phash else "0" * 16
        semantic_str = semantic_hash if semantic_hash else "0" * 64
        combined = sha256_hash + phash_str + semantic_str

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
                gop.semantic_hash,
                getattr(gop, 'vif', None),
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
                    gop.semantic_hash,
                    getattr(gop, 'vif', None),
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


# ============================================================================
# Hierarchical Merkle Tree for Time-Based GOP Aggregation
# ============================================================================

@dataclass
class ChunkData:
    """Represents a 30-second chunk of GOPs."""
    chunk_index: int
    start_time: float
    end_time: float
    gop_leaf_hashes: List[str]
    merkle_tree: Optional["MerkleTree"] = None
    chunk_root: Optional[str] = None

    def close(self) -> None:
        """Build Merkle tree and compute chunk root."""
        if not self.gop_leaf_hashes:
            raise ValueError(f"Chunk {self.chunk_index} has no GOPs")
        self.merkle_tree = MerkleTree(self.gop_leaf_hashes)
        self.chunk_root = self.merkle_tree.root


@dataclass
class SegmentData:
    """Represents a 5-minute segment of chunks."""
    segment_index: int
    start_time: float
    end_time: float
    chunks: List[ChunkData] = field(default_factory=list)
    merkle_tree: Optional["MerkleTree"] = None
    segment_root: Optional[str] = None

    def close(self) -> str:
        """Build Merkle tree from chunk roots and return segment root."""
        if not self.chunks:
            raise ValueError(f"Segment {self.segment_index} has no chunks")

        # Ensure all chunks are closed
        for chunk in self.chunks:
            if chunk.chunk_root is None:
                chunk.close()

        chunk_roots = [chunk.chunk_root for chunk in self.chunks]
        self.merkle_tree = MerkleTree(chunk_roots)
        self.segment_root = self.merkle_tree.root
        return self.segment_root


class HierarchicalMerkleTree:
    """
    Three-level Merkle tree for time-based GOP aggregation.

    Structure:
    - Level 1 (Leaves): Individual GOP leaf hashes
    - Level 2 (Chunks): 30-second windows → ChunkRoots
    - Level 3 (Segments): 5-minute windows → SegmentRoots

    Features:
    - Incremental anchoring (SegmentRoots every 5 minutes)
    - Precise tampering localization (30-second granularity)
    - Efficient verification (shorter proof paths)
    """

    def __init__(self, chunk_duration: float = 30.0, segment_duration: float = 300.0):
        """
        Initialize hierarchical Merkle tree.

        Args:
            chunk_duration: Seconds per chunk (default 30s)
            segment_duration: Seconds per segment (default 5min = 300s)
        """
        self._chunk_duration = chunk_duration
        self._segment_duration = segment_duration

        # Current working structures
        self._current_chunk: Optional[ChunkData] = None
        self._current_segment: Optional[SegmentData] = None

        # Closed segments
        self._closed_segments: List[SegmentData] = []

        # Mapping indices
        self._gop_to_chunk_map: Dict[int, int] = {}  # gop_index -> chunk_index
        self._chunk_to_segment_map: Dict[int, int] = {}  # chunk_index -> segment_index

        # Global counters
        self._global_gop_index = 0
        self._global_chunk_index = 0
        self._global_segment_index = 0

    def add_gop(self, leaf_hash: str, timestamp: float) -> None:
        """
        Add a GOP leaf hash at given timestamp. Auto-manages chunk/segment boundaries.

        Auto-close logic (time-based):
        - Chunk closes when: timestamp >= chunk_start_time + chunk_duration (30s)
        - Segment closes when: timestamp >= segment_start_time + segment_duration (5min)

        Args:
            leaf_hash: GOP leaf hash (from compute_leaf_hash)
            timestamp: GOP timestamp in seconds (Unix epoch or relative)
        """
        # Check if we need to close current segment (time-based) BEFORE processing
        if self._current_segment and timestamp >= self._current_segment.start_time + self._segment_duration:
            self.close_segment()

        # Initialize first chunk if needed
        if self._current_chunk is None:
            self._start_new_chunk(timestamp)

        # Check if we need to close current chunk (time-based)
        if timestamp >= self._current_chunk.start_time + self._chunk_duration:
            self._close_current_chunk(timestamp)
            self._start_new_chunk(timestamp)

        # Add GOP to current chunk
        self._current_chunk.gop_leaf_hashes.append(leaf_hash)
        self._gop_to_chunk_map[self._global_gop_index] = self._current_chunk.chunk_index
        self._global_gop_index += 1

    def _start_new_chunk(self, timestamp: float) -> None:
        """Start a new chunk at given timestamp."""
        # Initialize segment if needed
        if self._current_segment is None:
            self._current_segment = SegmentData(
                segment_index=self._global_segment_index,
                start_time=timestamp,
                end_time=timestamp  # Will be updated when closed
            )
            self._global_segment_index += 1

        # Create new chunk
        self._current_chunk = ChunkData(
            chunk_index=self._global_chunk_index,
            start_time=timestamp,
            end_time=timestamp,  # Will be updated when closed
            gop_leaf_hashes=[]
        )
        self._global_chunk_index += 1

    def _close_current_chunk(self, end_time: float) -> None:
        """Close current chunk and add to current segment."""
        if self._current_chunk is None or not self._current_chunk.gop_leaf_hashes:
            return

        self._current_chunk.end_time = end_time
        self._current_chunk.close()

        # Add to current segment
        self._current_segment.chunks.append(self._current_chunk)
        self._chunk_to_segment_map[self._current_chunk.chunk_index] = self._current_segment.segment_index

    def close_segment(self) -> str:
        """
        Manually close current segment and return SegmentRoot.

        Typically called by external scheduler every 5 minutes or at video end.
        Auto-close in add_gop() handles most cases during normal recording.

        Returns:
            SegmentRoot hash

        Raises:
            ValueError: If no segment to close
        """
        if self._current_segment is None:
            raise ValueError("No segment to close")

        # Close current chunk if it has GOPs
        if self._current_chunk and self._current_chunk.gop_leaf_hashes:
            self._close_current_chunk(self._current_chunk.start_time + self._chunk_duration)

        # Update segment end time
        if self._current_segment.chunks:
            self._current_segment.end_time = self._current_segment.chunks[-1].end_time

        # Close segment
        segment_root = self._current_segment.close()
        self._closed_segments.append(self._current_segment)

        # Reset current segment and chunk
        self._current_segment = None
        self._current_chunk = None

        return segment_root

    def get_full_proof(self, gop_index: int) -> dict:
        """
        Returns complete proof path from GOP leaf to SegmentRoot.

        Args:
            gop_index: Global GOP index (order of add_gop calls)

        Returns:
            {
                "gop_leaf_hash": str,
                "gop_to_chunk_proof": List[Dict[str, str]],
                "chunk_root": str,
                "chunk_to_segment_proof": List[Dict[str, str]],
                "segment_root": str,
                "chunk_index": int,
                "gop_index_in_chunk": int,
                "segment_index": int
            }

        Raises:
            ValueError: If gop_index not found or segment not closed
        """
        # Find chunk containing this GOP
        if gop_index not in self._gop_to_chunk_map:
            raise ValueError(f"GOP index {gop_index} not found")

        chunk_index = self._gop_to_chunk_map[gop_index]

        # Find segment containing this chunk
        if chunk_index not in self._chunk_to_segment_map:
            raise ValueError(f"Segment containing GOP {gop_index} not closed. Call close_segment() first.")

        segment_index = self._chunk_to_segment_map[chunk_index]

        # Get segment (must be closed)
        if segment_index >= len(self._closed_segments):
            raise ValueError(f"Segment {segment_index} not closed. Call close_segment() first.")

        segment = self._closed_segments[segment_index]

        # Find chunk in segment
        chunk = None
        chunk_index_in_segment = None
        for i, c in enumerate(segment.chunks):
            if c.chunk_index == chunk_index:
                chunk = c
                chunk_index_in_segment = i
                break

        if chunk is None:
            raise ValueError(f"Chunk {chunk_index} not found in segment {segment_index}")

        # Find GOP index within chunk
        gop_index_in_chunk = None
        gop_count = 0
        for gop_idx, chunk_idx in self._gop_to_chunk_map.items():
            if chunk_idx == chunk_index:
                if gop_idx == gop_index:
                    gop_index_in_chunk = gop_count
                    break
                gop_count += 1

        if gop_index_in_chunk is None:
            raise ValueError(f"GOP {gop_index} not found in chunk {chunk_index}")

        # Get proofs
        gop_to_chunk_proof = chunk.merkle_tree.get_proof(gop_index_in_chunk)
        chunk_to_segment_proof = segment.merkle_tree.get_proof(chunk_index_in_segment)

        return {
            "leaf_hash": chunk.gop_leaf_hashes[gop_index_in_chunk],
            "gop_to_chunk_proof": gop_to_chunk_proof,
            "chunk_root": chunk.chunk_root,
            "chunk_to_segment_proof": chunk_to_segment_proof,
            "segment_root": segment.segment_root,
            "chunk_index": chunk_index,
            "gop_index_in_chunk": gop_index_in_chunk,
            "segment_index": segment_index
        }

    def verify_full_proof(self, proof_data: dict) -> bool:
        """
        Verify a full hierarchical proof.

        Args:
            proof_data: Output from get_full_proof()

        Returns:
            True if proof is valid, False otherwise
        """
        # Verify GOP to ChunkRoot
        computed_chunk_root = apply_merkle_proof(
            proof_data["leaf_hash"],
            proof_data["gop_to_chunk_proof"]
        )
        if computed_chunk_root != proof_data["chunk_root"]:
            return False

        # Verify ChunkRoot to SegmentRoot
        computed_segment_root = apply_merkle_proof(
            proof_data["chunk_root"],
            proof_data["chunk_to_segment_proof"]
        )
        return computed_segment_root == proof_data["segment_root"]

    def locate_tampered_gops(self, gop_leaf_hashes: List[str]) -> List[int]:
        """
        Given a list of recomputed GOP hashes, identify which GOPs differ from original tree.

        Args:
            gop_leaf_hashes: List of leaf hashes in same order as original add_gop calls

        Returns:
            List of GOP indices that don't match original tree

        Raises:
            ValueError: If length of gop_leaf_hashes doesn't match total GOPs in tree

        Design Note:
            This implementation compares leaf hashes directly rather than accepting a
            segment_root parameter (as in original spec). This approach is more practical:
            - Direct comparison: O(n) scan vs O(n log n) tree rebuild
            - Clearer semantics: "which leaves changed?" vs "does root match?"
            - Better error reporting: Returns all tampered indices, not just boolean
        """
        # Collect all original leaf hashes in order
        original_leaves = []
        for gop_idx in range(self._global_gop_index):
            if gop_idx not in self._gop_to_chunk_map:
                continue

            chunk_idx = self._gop_to_chunk_map[gop_idx]
            segment_idx = self._chunk_to_segment_map.get(chunk_idx)

            if segment_idx is None or segment_idx >= len(self._closed_segments):
                continue

            segment = self._closed_segments[segment_idx]

            # Find chunk and GOP within it
            for chunk in segment.chunks:
                if chunk.chunk_index == chunk_idx:
                    # Find GOP position in chunk
                    gop_position = 0
                    for g_idx, c_idx in self._gop_to_chunk_map.items():
                        if c_idx == chunk_idx and g_idx < gop_idx:
                            gop_position += 1

                    if gop_position < len(chunk.gop_leaf_hashes):
                        original_leaves.append(chunk.gop_leaf_hashes[gop_position])
                    break

        # Validate input length
        if len(gop_leaf_hashes) != len(original_leaves):
            raise ValueError(
                f"Input length mismatch: expected {len(original_leaves)} hashes, got {len(gop_leaf_hashes)}"
            )

        # Compare with provided hashes
        tampered = []
        for i, (original, provided) in enumerate(zip(original_leaves, gop_leaf_hashes)):
            if original != provided:
                tampered.append(i)

        return tampered

    def get_all_segment_roots(self) -> List[str]:
        """Return all closed SegmentRoots (for blockchain anchoring)."""
        return [seg.segment_root for seg in self._closed_segments]

    def to_json(self) -> str:
        """Serialize entire three-level tree structure to JSON."""
        def chunk_to_dict(chunk: ChunkData) -> dict:
            return {
                "chunk_index": chunk.chunk_index,
                "start_time": chunk.start_time,
                "end_time": chunk.end_time,
                "gop_leaf_hashes": chunk.gop_leaf_hashes,
                "chunk_root": chunk.chunk_root,
                "merkle_tree": chunk.merkle_tree.to_json() if chunk.merkle_tree else None
            }

        def segment_to_dict(segment: SegmentData) -> dict:
            return {
                "segment_index": segment.segment_index,
                "start_time": segment.start_time,
                "end_time": segment.end_time,
                "segment_root": segment.segment_root,
                "chunks": [chunk_to_dict(c) for c in segment.chunks],
                "merkle_tree": segment.merkle_tree.to_json() if segment.merkle_tree else None
            }

        return json.dumps({
            "chunk_duration": self._chunk_duration,
            "segment_duration": self._segment_duration,
            "closed_segments": [segment_to_dict(s) for s in self._closed_segments],
            "current_segment": segment_to_dict(self._current_segment) if self._current_segment else None,
            "current_chunk": chunk_to_dict(self._current_chunk) if self._current_chunk else None,
            "gop_to_chunk_map": {str(k): v for k, v in self._gop_to_chunk_map.items()},
            "chunk_to_segment_map": {str(k): v for k, v in self._chunk_to_segment_map.items()},
            "global_gop_index": self._global_gop_index,
            "global_chunk_index": self._global_chunk_index,
            "global_segment_index": self._global_segment_index
        })

    @staticmethod
    def from_json(json_str: str) -> "HierarchicalMerkleTree":
        """Deserialize from JSON."""
        data = json.loads(json_str)

        obj = HierarchicalMerkleTree(
            chunk_duration=data["chunk_duration"],
            segment_duration=data["segment_duration"]
        )

        def dict_to_chunk(d: dict) -> ChunkData:
            chunk = ChunkData(
                chunk_index=d["chunk_index"],
                start_time=d["start_time"],
                end_time=d["end_time"],
                gop_leaf_hashes=d["gop_leaf_hashes"],
                chunk_root=d["chunk_root"]
            )
            if d["merkle_tree"]:
                chunk.merkle_tree = MerkleTree.from_json(d["merkle_tree"])
            return chunk

        def dict_to_segment(d: dict) -> SegmentData:
            segment = SegmentData(
                segment_index=d["segment_index"],
                start_time=d["start_time"],
                end_time=d["end_time"],
                segment_root=d["segment_root"],
                chunks=[dict_to_chunk(c) for c in d["chunks"]]
            )
            if d["merkle_tree"]:
                segment.merkle_tree = MerkleTree.from_json(d["merkle_tree"])
            return segment

        obj._closed_segments = [dict_to_segment(s) for s in data["closed_segments"]]
        obj._current_segment = dict_to_segment(data["current_segment"]) if data["current_segment"] else None
        obj._current_chunk = dict_to_chunk(data["current_chunk"]) if data["current_chunk"] else None
        obj._gop_to_chunk_map = {int(k): v for k, v in data["gop_to_chunk_map"].items()}
        obj._chunk_to_segment_map = {int(k): v for k, v in data["chunk_to_segment_map"].items()}
        obj._global_gop_index = data["global_gop_index"]
        obj._global_chunk_index = data["global_chunk_index"]
        obj._global_segment_index = data["global_segment_index"]

        return obj


# ============================================================================
# EpochMerkleTree: Cross-device segment aggregation
# ============================================================================

@dataclass
class DeviceSegment:
    """Represents one device's contribution to an epoch"""
    device_id: str
    segment_root: str
    timestamp: str  # ISO format
    semantic_summaries: List[str]
    gop_count: int


class EpochMerkleTree:
    """
    Aggregates SegmentRoots from multiple devices into a single EpochRoot.
    Each device contributes one leaf (its SegmentRoot) per epoch.
    """

    def __init__(self, epoch_id: str):
        """
        Args:
            epoch_id: Unique identifier for this epoch (e.g., "epoch_20260316_142500")
        """
        self._epoch_id = epoch_id
        self._devices: Dict[str, DeviceSegment] = {}  # device_id -> DeviceSegment (deduplication)
        self._merkle_tree: Optional[MerkleTree] = None
        self._epoch_root: Optional[str] = None
        self._device_index_map: Dict[str, int] = {}  # device_id -> leaf_index

    def add_device_segment(self, device_segment: DeviceSegment) -> None:
        """
        Add a device's SegmentRoot to this epoch.
        If device already exists, overwrites with latest report (last-write-wins).
        """
        if self._merkle_tree is not None:
            raise ValueError("Cannot add devices after tree is built")
        self._devices[device_segment.device_id] = device_segment

    def build_tree(self) -> str:
        """Build Merkle tree from all device SegmentRoots and return EpochRoot."""
        if len(self._devices) == 0:
            raise ValueError("Cannot build tree with no devices")

        # Sort devices by device_id for deterministic ordering
        sorted_devices = sorted(self._devices.values(), key=lambda d: d.device_id)

        # Use SegmentRoots as leaves
        leaves = [d.segment_root for d in sorted_devices]
        self._merkle_tree = MerkleTree(leaves)
        self._epoch_root = self._merkle_tree.root

        # Build device index map
        for idx, device in enumerate(sorted_devices):
            self._device_index_map[device.device_id] = idx

        return self._epoch_root

    def get_device_proof(self, device_id: str) -> Dict:
        """Get Merkle proof for a specific device's SegmentRoot."""
        if self._merkle_tree is None:
            raise ValueError("Tree not built yet")
        if device_id not in self._device_index_map:
            raise ValueError(f"Device {device_id} not in this epoch")

        leaf_index = self._device_index_map[device_id]
        device = self._devices[device_id]
        proof = self._merkle_tree.get_proof(leaf_index)

        return {
            "epoch_id": self._epoch_id,
            "device_id": device_id,
            "segment_root": device.segment_root,
            "epoch_root": self._epoch_root,
            "proof": proof,
            "leaf_index": leaf_index
        }

    def verify_device_proof(self, proof_data: Dict) -> bool:
        """Verify a device's proof against the EpochRoot."""
        return MerkleTree.verify_proof(
            proof_data["segment_root"],
            proof_data["proof"],
            proof_data["epoch_root"]
        )

    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "epoch_id": self._epoch_id,
            "epoch_root": self._epoch_root,
            "devices": [
                {
                    "device_id": d.device_id,
                    "segment_root": d.segment_root,
                    "timestamp": d.timestamp,
                    "semantic_summaries": d.semantic_summaries,
                    "gop_count": d.gop_count
                }
                for d in self._devices.values()
            ],
            "merkle_tree": self._merkle_tree.to_json() if self._merkle_tree else None
        }

    @staticmethod
    def from_dict(data: Dict) -> "EpochMerkleTree":
        """Deserialize from dictionary."""
        tree = EpochMerkleTree(data["epoch_id"])
        for device_data in data["devices"]:
            tree.add_device_segment(DeviceSegment(**device_data))
        if data["merkle_tree"]:
            tree._merkle_tree = MerkleTree.from_json(data["merkle_tree"])
            tree._epoch_root = data["epoch_root"]
            # Sort devices by device_id for deterministic ordering
            sorted_devices = sorted(tree._devices.values(), key=lambda d: d.device_id)
            for idx, device in enumerate(sorted_devices):
                tree._device_index_map[device.device_id] = idx
        return tree

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())

    @staticmethod
    def from_json(json_str: str) -> "EpochMerkleTree":
        """Deserialize from JSON string."""
        return EpochMerkleTree.from_dict(json.loads(json_str))
