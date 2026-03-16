"""
Unit tests for EpochMerkleTree.

Tests:
1. Basic tree construction with multiple devices
2. Proof generation and verification
3. Serialization/deserialization
4. Deduplication (same device reports twice)
5. Edge cases (empty tree, single device)
"""

import hashlib
import json
from datetime import datetime, timezone

import pytest

from services.merkle_utils import DeviceSegment, EpochMerkleTree, MerkleTree


def generate_test_hash(content: str) -> str:
    """Generate a test hash from content."""
    return hashlib.sha256(content.encode()).hexdigest()


def create_test_device_segment(device_id: str, index: int = 0) -> DeviceSegment:
    """Create a test DeviceSegment."""
    return DeviceSegment(
        device_id=device_id,
        segment_root=generate_test_hash(f"{device_id}_segment_{index}"),
        timestamp=datetime.now(timezone.utc).isoformat(),
        semantic_summaries=[f"Summary {i}" for i in range(3)],
        gop_count=150 + index,
    )


class TestEpochMerkleTree:
    """Test suite for EpochMerkleTree."""

    def test_basic_tree_construction(self):
        """Test building a tree with 3 devices."""
        epoch_id = "epoch_test_001"
        tree = EpochMerkleTree(epoch_id)

        # Add 3 devices
        devices = [
            create_test_device_segment("cam_001", 0),
            create_test_device_segment("cam_002", 1),
            create_test_device_segment("cam_003", 2),
        ]

        for device in devices:
            tree.add_device_segment(device)

        # Build tree
        epoch_root = tree.build_tree()

        # Verify
        assert epoch_root is not None
        assert len(epoch_root) == 64  # SHA-256 hex
        assert len(tree._devices) == 3
        assert tree._epoch_root == epoch_root

    def test_proof_generation_and_verification(self):
        """Test generating and verifying proofs for each device."""
        epoch_id = "epoch_test_002"
        tree = EpochMerkleTree(epoch_id)

        # Add 3 devices
        device_ids = ["cam_001", "cam_002", "cam_003"]
        for device_id in device_ids:
            tree.add_device_segment(create_test_device_segment(device_id))

        epoch_root = tree.build_tree()

        # Test proof for each device
        for device_id in device_ids:
            proof_data = tree.get_device_proof(device_id)

            # Verify proof structure
            assert proof_data["epoch_id"] == epoch_id
            assert proof_data["device_id"] == device_id
            assert proof_data["epoch_root"] == epoch_root
            assert "segment_root" in proof_data
            assert "proof" in proof_data
            assert "leaf_index" in proof_data

            # Verify proof
            assert tree.verify_device_proof(proof_data) is True

    def test_serialization_deserialization(self):
        """Test to_dict/from_dict and to_json/from_json."""
        epoch_id = "epoch_test_003"
        tree = EpochMerkleTree(epoch_id)

        # Add devices
        for i in range(3):
            tree.add_device_segment(create_test_device_segment(f"cam_{i:03d}", i))

        epoch_root = tree.build_tree()

        # Test dict serialization
        tree_dict = tree.to_dict()
        assert tree_dict["epoch_id"] == epoch_id
        assert tree_dict["epoch_root"] == epoch_root
        assert len(tree_dict["devices"]) == 3

        # Test dict deserialization
        restored_tree = EpochMerkleTree.from_dict(tree_dict)
        assert restored_tree._epoch_id == epoch_id
        assert restored_tree._epoch_root == epoch_root
        assert len(restored_tree._devices) == 3

        # Verify proofs still work
        proof = restored_tree.get_device_proof("cam_001")
        assert restored_tree.verify_device_proof(proof) is True

        # Test JSON serialization
        tree_json = tree.to_json()
        assert isinstance(tree_json, str)

        # Test JSON deserialization
        restored_from_json = EpochMerkleTree.from_json(tree_json)
        assert restored_from_json._epoch_id == epoch_id
        assert restored_from_json._epoch_root == epoch_root

    def test_deduplication(self):
        """Test that duplicate device reports use last-write-wins."""
        epoch_id = "epoch_test_004"
        tree = EpochMerkleTree(epoch_id)

        # Add device twice with different data
        device1 = create_test_device_segment("cam_001", 0)
        device2 = create_test_device_segment("cam_001", 1)  # Same device, different data

        tree.add_device_segment(device1)
        tree.add_device_segment(device2)  # Should overwrite

        # Build tree
        tree.build_tree()

        # Verify only one device in tree
        assert len(tree._devices) == 1

        # Verify it's the second report (last-write-wins)
        stored_device = tree._devices["cam_001"]
        assert stored_device.segment_root == device2.segment_root
        assert stored_device.gop_count == device2.gop_count

    def test_cannot_add_after_build(self):
        """Test that adding devices after build_tree raises error."""
        tree = EpochMerkleTree("epoch_test_005")
        tree.add_device_segment(create_test_device_segment("cam_001"))
        tree.build_tree()

        # Try to add another device
        with pytest.raises(ValueError, match="Cannot add devices after tree is built"):
            tree.add_device_segment(create_test_device_segment("cam_002"))

    def test_empty_tree_error(self):
        """Test that building empty tree raises error."""
        tree = EpochMerkleTree("epoch_test_006")

        with pytest.raises(ValueError, match="Cannot build tree with no devices"):
            tree.build_tree()

    def test_single_device(self):
        """Test tree with single device."""
        tree = EpochMerkleTree("epoch_test_007")
        tree.add_device_segment(create_test_device_segment("cam_001"))

        epoch_root = tree.build_tree()

        # Verify tree built successfully
        assert epoch_root is not None
        assert len(tree._devices) == 1

        # Verify proof works
        proof = tree.get_device_proof("cam_001")
        assert tree.verify_device_proof(proof) is True

    def test_proof_for_nonexistent_device(self):
        """Test that getting proof for nonexistent device raises error."""
        tree = EpochMerkleTree("epoch_test_008")
        tree.add_device_segment(create_test_device_segment("cam_001"))
        tree.build_tree()

        with pytest.raises(ValueError, match="Device cam_999 not in this epoch"):
            tree.get_device_proof("cam_999")

    def test_proof_before_build(self):
        """Test that getting proof before build raises error."""
        tree = EpochMerkleTree("epoch_test_009")
        tree.add_device_segment(create_test_device_segment("cam_001"))

        with pytest.raises(ValueError, match="Tree not built yet"):
            tree.get_device_proof("cam_001")

    def test_deterministic_ordering(self):
        """Test that device ordering is deterministic (sorted by device_id)."""
        tree1 = EpochMerkleTree("epoch_test_010")
        tree2 = EpochMerkleTree("epoch_test_010")

        # Add devices in different order
        devices = [
            create_test_device_segment("cam_003", 0),
            create_test_device_segment("cam_001", 1),
            create_test_device_segment("cam_002", 2),
        ]

        # Tree 1: add in order [3, 1, 2]
        for device in devices:
            tree1.add_device_segment(device)

        # Tree 2: add in order [1, 2, 3]
        for device in sorted(devices, key=lambda d: d.device_id):
            tree2.add_device_segment(device)

        # Build both trees
        root1 = tree1.build_tree()
        root2 = tree2.build_tree()

        # Roots should be identical (deterministic ordering)
        assert root1 == root2

        # Leaf indices should match
        assert tree1._device_index_map == tree2._device_index_map

    def test_large_tree(self):
        """Test tree with many devices (stress test)."""
        tree = EpochMerkleTree("epoch_test_011")

        # Add 100 devices
        num_devices = 100
        for i in range(num_devices):
            tree.add_device_segment(create_test_device_segment(f"cam_{i:03d}", i))

        epoch_root = tree.build_tree()

        # Verify tree built successfully
        assert epoch_root is not None
        assert len(tree._devices) == num_devices

        # Verify random proofs
        test_devices = ["cam_000", "cam_050", "cam_099"]
        for device_id in test_devices:
            proof = tree.get_device_proof(device_id)
            assert tree.verify_device_proof(proof) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
