"""Unit tests for HierarchicalMerkleTree."""
import hashlib
import json
import pytest
from services.merkle_utils import HierarchicalMerkleTree


def _create_test_gops(count: int, start_time: float = 1700000000.0, interval: float = 2.0):
    """Generate (leaf_hash, timestamp) tuples for testing."""
    gops = []
    for i in range(count):
        content = f"GOP_{i}".encode()
        leaf_hash = hashlib.sha256(content).hexdigest()
        timestamp = start_time + i * interval
        gops.append((leaf_hash, timestamp))
    return gops


def test_single_gop():
    """Test that a single GOP creates minimal structure."""
    tree = HierarchicalMerkleTree()
    leaf_hash = hashlib.sha256(b"GOP_0").hexdigest()
    tree.add_gop(leaf_hash, 1700000000.0)

    # Should have current chunk but no closed segments yet
    assert tree._current_chunk is not None
    assert len(tree._current_chunk.gop_leaf_hashes) == 1
    assert len(tree._closed_segments) == 0

    # Close segment manually
    segment_root = tree.close_segment()
    assert segment_root is not None
    assert len(tree._closed_segments) == 1


def test_chunk_auto_close():
    """Test that adding GOP after 30s closes chunk."""
    tree = HierarchicalMerkleTree(chunk_duration=30.0)

    # Add GOP at t=0
    leaf1 = hashlib.sha256(b"GOP_0").hexdigest()
    tree.add_gop(leaf1, 1700000000.0)
    assert tree._current_chunk is not None
    assert len(tree._current_chunk.gop_leaf_hashes) == 1

    # Add GOP at t=31s (should close first chunk)
    leaf2 = hashlib.sha256(b"GOP_1").hexdigest()
    tree.add_gop(leaf2, 1700000031.0)

    # Should have new chunk with 1 GOP, and segment should have 1 closed chunk
    assert len(tree._current_chunk.gop_leaf_hashes) == 1
    assert len(tree._current_segment.chunks) == 1
    assert tree._current_segment.chunks[0].chunk_root is not None


def test_segment_auto_close():
    """Test that adding GOP after 5min auto-closes segment (time-based)."""
    tree = HierarchicalMerkleTree(chunk_duration=30.0, segment_duration=300.0)

    # Add GOPs for 5 minutes (every 2s = 150 GOPs)
    start_time = 1700000000.0
    for i in range(150):
        leaf = hashlib.sha256(f"GOP_{i}".encode()).hexdigest()
        tree.add_gop(leaf, start_time + i * 2.0)

    # Should have current segment with chunks, no closed segments yet
    assert len(tree._closed_segments) == 0
    assert tree._current_segment is not None

    # Add GOP at t=301s (should auto-close first segment)
    leaf = hashlib.sha256(b"GOP_150").hexdigest()
    tree.add_gop(leaf, start_time + 301.0)

    # Should have 1 closed segment and new current segment
    assert len(tree._closed_segments) == 1
    assert tree._current_segment is not None
    assert tree._closed_segments[0].segment_root is not None


def test_10min_video_simulation():
    """Main test: Simulate 10 minutes of GOPs (2s interval = 300 GOPs)."""
    tree = HierarchicalMerkleTree(chunk_duration=30.0, segment_duration=300.0)

    # Add 300 GOPs at 2s intervals (10 minutes total)
    gops = _create_test_gops(300, start_time=1700000000.0, interval=2.0)
    for leaf_hash, timestamp in gops:
        tree.add_gop(leaf_hash, timestamp)

    # Close final segment
    tree.close_segment()

    # Verify 2 segments created (5min each)
    assert len(tree._closed_segments) == 2

    # Verify each segment has ~10 chunks (with uniform 2s GOPs, should be exactly 10)
    for segment in tree._closed_segments:
        # With 300s segment and 30s chunks, expect 10 chunks
        assert len(segment.chunks) == 10

        # Verify each chunk has ~15 GOPs (300s/10 chunks = 30s per chunk, 30s/2s = 15 GOPs)
        for chunk in segment.chunks:
            assert len(chunk.gop_leaf_hashes) == 15


def test_full_proof_verification():
    """Generate and verify proof for arbitrary GOP."""
    tree = HierarchicalMerkleTree()

    # Add 100 GOPs
    gops = _create_test_gops(100)
    for leaf_hash, timestamp in gops:
        tree.add_gop(leaf_hash, timestamp)

    # Close segment
    tree.close_segment()

    # Get proof for GOP at index 50
    proof = tree.get_full_proof(50)

    # Verify proof structure
    assert "gop_to_chunk_proof" in proof
    assert "chunk_to_segment_proof" in proof
    assert "leaf_hash" in proof
    assert "chunk_root" in proof
    assert "segment_root" in proof
    assert "chunk_index" in proof
    assert "gop_index_in_chunk" in proof
    assert "segment_index" in proof

    # Verify proof is valid
    assert tree.verify_full_proof(proof) is True

    # Tamper with leaf hash and verify proof fails
    tampered_proof = proof.copy()
    tampered_proof["leaf_hash"] = "0" * 64
    assert tree.verify_full_proof(tampered_proof) is False


def test_tampered_gop_detection():
    """Modify one GOP hash, verify locate_tampered_gops() finds it."""
    tree = HierarchicalMerkleTree()

    # Add 100 GOPs
    gops = _create_test_gops(100)
    original_leaves = []
    for leaf_hash, timestamp in gops:
        tree.add_gop(leaf_hash, timestamp)
        original_leaves.append(leaf_hash)

    tree.close_segment()

    # Create tampered list (modify GOP at index 50)
    tampered_leaves = original_leaves.copy()
    tampered_leaves[50] = "0" * 64

    # Locate tampered GOPs
    tampered_indices = tree.locate_tampered_gops(tampered_leaves)

    # Should find exactly one tampered GOP at index 50
    assert len(tampered_indices) == 1
    assert 50 in tampered_indices

    # Test with multiple tampered GOPs
    tampered_leaves[25] = "1" * 64
    tampered_leaves[75] = "2" * 64
    tampered_indices = tree.locate_tampered_gops(tampered_leaves)
    assert len(tampered_indices) == 3
    assert 25 in tampered_indices
    assert 50 in tampered_indices
    assert 75 in tampered_indices


def test_serialization():
    """Test to_json/from_json round-trip."""
    tree = HierarchicalMerkleTree()

    # Add some GOPs
    gops = _create_test_gops(50)
    for leaf_hash, timestamp in gops:
        tree.add_gop(leaf_hash, timestamp)

    tree.close_segment()

    # Serialize
    json_str = tree.to_json()
    assert json_str is not None

    # Deserialize
    restored_tree = HierarchicalMerkleTree.from_json(json_str)

    # Verify structure matches
    assert len(restored_tree._closed_segments) == len(tree._closed_segments)
    assert restored_tree._chunk_duration == tree._chunk_duration
    assert restored_tree._segment_duration == tree._segment_duration

    # Verify segment roots match
    original_roots = tree.get_all_segment_roots()
    restored_roots = restored_tree.get_all_segment_roots()
    assert original_roots == restored_roots


def test_manual_segment_close():
    """Close segment before 5min (video end scenario)."""
    tree = HierarchicalMerkleTree()

    # Add only 50 GOPs (100 seconds, less than 5 minutes)
    gops = _create_test_gops(50)
    for leaf_hash, timestamp in gops:
        tree.add_gop(leaf_hash, timestamp)

    # Manually close segment
    segment_root = tree.close_segment()

    # Should have 1 closed segment
    assert len(tree._closed_segments) == 1
    assert segment_root is not None
    assert tree._closed_segments[0].segment_root == segment_root


def test_edge_cases():
    """Test empty tree, single chunk, non-aligned timestamps."""
    # Test get_full_proof on unclosed segment
    tree = HierarchicalMerkleTree()
    leaf = hashlib.sha256(b"GOP_0").hexdigest()
    tree.add_gop(leaf, 1700000000.0)

    with pytest.raises(ValueError, match="Segment.*not closed"):
        tree.get_full_proof(0)

    # Test locate_tampered_gops with wrong length
    tree.close_segment()
    with pytest.raises(ValueError, match="length mismatch"):
        tree.locate_tampered_gops([leaf, leaf])  # Wrong length

    # Test non-aligned timestamps (GOPs at irregular intervals)
    tree2 = HierarchicalMerkleTree()
    timestamps = [1700000000.0, 1700000003.0, 1700000007.0, 1700000015.0, 1700000032.0]
    for i, ts in enumerate(timestamps):
        leaf = hashlib.sha256(f"GOP_{i}".encode()).hexdigest()
        tree2.add_gop(leaf, ts)

    # Should handle irregular intervals correctly
    tree2.close_segment()
    assert len(tree2._closed_segments) == 1
    # First 4 GOPs in first chunk (before 30s), last GOP in second chunk (after 30s)
    assert len(tree2._closed_segments[0].chunks) == 2
