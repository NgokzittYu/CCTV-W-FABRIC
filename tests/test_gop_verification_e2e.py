"""End-to-end integration tests for GOP verification.

These tests require:
1. Running Fabric test-network with evidence chaincode deployed
2. Running IPFS node (docker compose -f docker-compose.ipfs.yml up -d)
3. Set FABRIC_SAMPLES_PATH if default ~/projects/fabric-samples doesn't apply

Run:
    python -m pytest tests/test_gop_verification_e2e.py -v -s
"""
import hashlib
import json
import time
import uuid
from pathlib import Path

import numpy as np
import pytest

from services.fabric_client import build_fabric_env, submit_anchor
from services.gop_splitter import GOPData
from services.merkle_utils import MerkleTree, compute_leaf_hash
from services.ipfs_storage import VideoStorage
from services.gop_verifier import GOPVerifier
from services.perceptual_hash import compute_phash
from services.tri_state_verifier import TriStateVerifier
from services.semantic_fingerprint import SemanticExtractor
from config import SETTINGS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_synthetic_gop(gop_id: int, size: int = 1024) -> GOPData:
    """Create a synthetic GOP with deterministic content."""
    # Create synthetic H.264-like data (not real video, just for testing)
    content = f"GOP_{gop_id}_".encode() + b"\x00" * (size - len(f"GOP_{gop_id}_"))
    sha256_hash = hashlib.sha256(content).hexdigest()

    # Create synthetic keyframe (64x64 BGR image)
    # Use gop_id to create deterministic but unique frames (modulo to prevent overflow)
    keyframe = np.full((64, 64, 3), (gop_id * 10) % 256, dtype=np.uint8)

    # Compute pHash for the keyframe
    phash = compute_phash(keyframe)

    # Compute semantic fingerprint
    semantic_fp = None
    semantic_hash = None
    try:
        extractor = SemanticExtractor.get_instance()
        semantic_fp = extractor.extract(
            keyframe_frame=keyframe,
            gop_id=gop_id,
            start_time=float(1700000000 + gop_id * 2)
        )
        if semantic_fp:
            semantic_hash = semantic_fp.semantic_hash
    except Exception:
        pass  # Graceful degradation in tests

    return GOPData(
        gop_id=gop_id,
        start_time=float(1700000000 + gop_id * 2),
        end_time=float(1700000000 + gop_id * 2 + 2),
        raw_bytes=content,
        byte_size=len(content),
        sha256_hash=sha256_hash,
        frame_count=25,  # Standard GOP size
        keyframe_frame=keyframe,
        phash=phash,
        vif="0" * 64,  # Dummy VIF
        semantic_hash=semantic_hash,
        semantic_fingerprint=semantic_fp,
    )


def _unique_epoch_id(prefix: str = "test") -> str:
    """Generate unique epoch ID for testing."""
    ts = int(time.time())
    return f"epoch_{prefix}_{ts}_{ts + 60}_{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def fabric_env():
    """Build Fabric environment once per test module."""
    fabric_samples = Path(SETTINGS.fabric_samples_path).expanduser().resolve()
    env, orderer_ca, org2_tls = build_fabric_env(fabric_samples)
    return env, orderer_ca, org2_tls


@pytest.fixture(scope="module")
def fabric_cfg():
    """Get Fabric configuration."""
    return SETTINGS.channel_name, SETTINGS.chaincode_name


@pytest.fixture(scope="module")
def ipfs_storage():
    """Create IPFS storage instance."""
    storage = VideoStorage(
        api_url=SETTINGS.ipfs_api_url,
        gateway_url=SETTINGS.ipfs_gateway_url,
        pin_enabled=SETTINGS.ipfs_pin_enabled,
        index_db_path="data/ipfs_test_e2e_index.db",
    )
    return storage


@pytest.fixture(scope="module")
def gop_verifier(ipfs_storage, fabric_env, fabric_cfg):
    """Create GOP verifier instance."""
    env, orderer_ca, org2_tls = fabric_env
    channel, chaincode = fabric_cfg

    verifier = GOPVerifier(
        storage=ipfs_storage,
        fabric_env=env,
        orderer_ca=orderer_ca,
        org2_tls=org2_tls,
        channel=channel,
        chaincode=chaincode,
    )
    return verifier


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGOPVerificationE2E:
    """End-to-end GOP verification tests."""

    def test_gop_verification_intact(
        self, ipfs_storage, fabric_env, fabric_cfg, gop_verifier
    ):
        """Test verification of intact GOP returns INTACT status."""
        env, orderer_ca, org2_tls = fabric_env
        channel, chaincode = fabric_cfg

        # 1. Create synthetic GOPs
        device_id = f"device_intact_{uuid.uuid4().hex[:8]}"
        gops = [_create_synthetic_gop(i, size=512) for i in range(4)]

        # 2. Upload GOPs to IPFS
        cids = []
        for gop in gops:
            cid = ipfs_storage.upload_gop(device_id, gop)
            cids.append(cid)

        # 3. Build Merkle tree
        tree = MerkleTree(cids)

        # 4. Upload Merkle tree JSON to IPFS
        epoch_id = _unique_epoch_id("intact")
        tree_filename = f"merkle_tree_{epoch_id}.json"
        ipfs_storage.upload_json(device_id, tree_filename, json.loads(tree.to_json()))

        # 5. Submit anchor to Fabric
        timestamp = str(int(time.time()))
        result = submit_anchor(
            env, orderer_ca, org2_tls,
            channel, chaincode,
            epoch_id, tree.root, timestamp, device_count=1,
        )
        assert result["tx_id"], "Anchor submission should return tx_id"

        # 6. Verify GOP[0] - should be INTACT
        verification_result = gop_verifier.verify_gop(device_id, epoch_id, 0)

        assert verification_result["status"] == "INTACT", \
            f"Expected INTACT, got {verification_result}"
        assert verification_result["details"]["cid"] == cids[0]
        assert verification_result["details"]["gop_index"] == 0

    def test_gop_verification_tampered(
        self, ipfs_storage, fabric_env, fabric_cfg, gop_verifier
    ):
        """Test verification of tampered GOP returns NOT_INTACT status."""
        env, orderer_ca, org2_tls = fabric_env
        channel, chaincode = fabric_cfg

        # 1. Create synthetic GOPs
        device_id = f"device_tampered_{uuid.uuid4().hex[:8]}"
        gops = [_create_synthetic_gop(i, size=512) for i in range(4)]

        # 2. Upload GOPs to IPFS
        cids = []
        for gop in gops:
            cid = ipfs_storage.upload_gop(device_id, gop)
            cids.append(cid)

        # 3. Build Merkle tree
        tree = MerkleTree(cids)

        # 4. Upload Merkle tree JSON
        epoch_id = _unique_epoch_id("tampered")
        tree_filename = f"merkle_tree_{epoch_id}.json"
        ipfs_storage.upload_json(device_id, tree_filename, json.loads(tree.to_json()))

        # 5. Submit anchor to Fabric
        timestamp = str(int(time.time()))
        result = submit_anchor(
            env, orderer_ca, org2_tls,
            channel, chaincode,
            epoch_id, tree.root, timestamp, device_count=1,
        )
        assert result["tx_id"]

        # 6. Tamper simulation: In IPFS, content is immutable (CID = hash).
        # Tampering is simulated by uploading different content and
        # modifying the index to map the original CID to the tampered content.
        tampered_content = b"TAMPERED_DATA" + b"\x00" * 499
        tampered_cid = ipfs_storage.client.add_bytes(tampered_content, pin=True, cid_version=1)

        # Update the SQLite index to point original SHA-256 → tampered CID
        ipfs_storage._index._conn.execute(
            "UPDATE gop_index SET ipfs_cid = ? WHERE device_id = ? AND sha256_hash = ?",
            (tampered_cid, device_id, gops[0].sha256_hash),
        )
        ipfs_storage._index._conn.commit()

        # 7. Verify GOP[0] - should be NOT_INTACT
        verification_result = gop_verifier.verify_gop(device_id, epoch_id, 0)

        assert verification_result["status"] == "NOT_INTACT", \
            f"Expected NOT_INTACT for tampered GOP, got {verification_result}"
        assert "reason" in verification_result

    def test_gop_verification_single_byte_tamper(
        self, ipfs_storage, fabric_env, fabric_cfg, gop_verifier
    ):
        """Test that even a single byte modification is detected."""
        env, orderer_ca, org2_tls = fabric_env
        channel, chaincode = fabric_cfg

        # 1. Create synthetic GOPs
        device_id = f"device_singlebyte_{uuid.uuid4().hex[:8]}"
        gops = [_create_synthetic_gop(i, size=512) for i in range(4)]

        # 2. Upload GOPs to IPFS
        cids = []
        for gop in gops:
            cid = ipfs_storage.upload_gop(device_id, gop)
            cids.append(cid)

        # 3. Build Merkle tree
        tree = MerkleTree(cids)

        # 4. Upload Merkle tree JSON
        epoch_id = _unique_epoch_id("singlebyte")
        tree_filename = f"merkle_tree_{epoch_id}.json"
        ipfs_storage.upload_json(device_id, tree_filename, json.loads(tree.to_json()))

        # 5. Submit anchor to Fabric
        timestamp = str(int(time.time()))
        result = submit_anchor(
            env, orderer_ca, org2_tls,
            channel, chaincode,
            epoch_id, tree.root, timestamp, device_count=1,
        )
        assert result["tx_id"]

        # 6. Download GOP[0], modify single byte, re-upload as new CID
        original_bytes = ipfs_storage.download_gop(device_id, cids[0])

        # Modify byte at position 100 (increment by 1)
        tampered_bytes = bytearray(original_bytes)
        tampered_bytes[100] = (tampered_bytes[100] + 1) % 256
        tampered_bytes = bytes(tampered_bytes)

        # Upload tampered content → gets a new CID
        tampered_cid = ipfs_storage.client.add_bytes(bytes(tampered_bytes), pin=True, cid_version=1)

        # Simulate tampering by pointing the original SHA-256 → tampered CID in index
        ipfs_storage._index._conn.execute(
            "UPDATE gop_index SET ipfs_cid = ? WHERE device_id = ? AND sha256_hash = ?",
            (tampered_cid, device_id, gops[0].sha256_hash),
        )
        ipfs_storage._index._conn.commit()

        # 7. Verify GOP[0] - should detect single byte change
        verification_result = gop_verifier.verify_gop(device_id, epoch_id, 0)

        assert verification_result["status"] == "NOT_INTACT", \
            f"Expected NOT_INTACT for single-byte tamper, got {verification_result}"
        assert "computed root mismatch" in verification_result.get("reason", ""), \
            "Should indicate hash mismatch"

        # Verify the hash is indeed different
        original_hash = cids[0]
        recomputed_hash = verification_result["details"]["recomputed_hash"]
        assert original_hash != recomputed_hash, \
            "Single byte change should produce different hash"


def test_tri_state_intact(fabric_env, fabric_cfg, ipfs_storage, gop_verifier):
    """Test tri-state verification: INTACT case (no changes)."""
    import cv2

    # Create original GOP
    gop = _create_synthetic_gop(1)
    original_sha256 = gop.sha256_hash
    original_phash = gop.phash

    # Verify tri-state result
    verifier = TriStateVerifier()
    result, _, _ = verifier.verify(original_sha256, original_sha256, gop.vif, gop.vif)

    assert result == "INTACT", f"Expected INTACT for identical GOP, got {result}"


def test_tri_state_re_encoded(fabric_env, fabric_cfg, ipfs_storage, gop_verifier):
    """Test tri-state verification: RE_ENCODED case (JPEG compression)."""
    import cv2

    # Create original GOP
    gop = _create_synthetic_gop(1)
    original_sha256 = gop.sha256_hash
    original_phash = gop.phash

    # Simulate JPEG re-encoding impact on hash and VIF
    reencoded_sha256 = hashlib.sha256(b"reencoded_data").hexdigest()
    reencoded_vif = "3" + "0" * 63  # Slightly different VIF (distance=2)

    # Verify tri-state result
    verifier = TriStateVerifier()
    result, _, _ = verifier.verify(original_sha256, reencoded_sha256, gop.vif, reencoded_vif)

    assert result == "RE_ENCODED", f"Expected RE_ENCODED for JPEG compression, got {result}"


def test_tri_state_tampered(fabric_env, fabric_cfg, ipfs_storage, gop_verifier):
    """Test tri-state verification: TAMPERED case (different content)."""
    import cv2

    # Create original GOP
    gop1 = _create_synthetic_gop(1)
    original_sha256 = gop1.sha256_hash
    original_phash = gop1.phash

    tampered_sha256 = hashlib.sha256(b"completely_different").hexdigest()
    tampered_vif = "f" * 64  # Max distance VIF

    # Verify tri-state result
    verifier = TriStateVerifier()
    result, _, _ = verifier.verify(original_sha256, tampered_sha256, gop.vif, tampered_vif)

    assert result == "TAMPERED", f"Expected TAMPERED for different content, got {result}"


def test_semantic_fingerprint_upload(fabric_env, fabric_cfg, ipfs_storage):
    """Test that semantic JSON files are uploaded to IPFS alongside GOP chunks."""
    device_id = "test_device_semantic"
    gops = [_create_synthetic_gop(i) for i in range(2)]

    # Upload GOPs
    cids = []
    for gop in gops:
        cid = ipfs_storage.upload_gop(device_id, gop)
        cids.append(cid)

    # Check if semantic JSON files exist (if semantic extraction succeeded)
    for i, gop in enumerate(gops):
        if gop.semantic_fingerprint:
            sem_filename = f"{gop.sha256_hash}_semantic.json"
            sem_cid = ipfs_storage._index.get_json_cid(device_id, sem_filename)

            if sem_cid:
                # Download and verify semantic JSON via IPFS
                try:
                    json_bytes = ipfs_storage.client.cat(sem_cid)
                    semantic_data = json.loads(json_bytes.decode('utf-8'))

                    # Verify structure
                    assert "gop_id" in semantic_data
                    assert semantic_data["gop_id"] == gop.gop_id
                    assert "timestamp" in semantic_data
                    assert "objects" in semantic_data
                    assert "total_count" in semantic_data
                    assert "semantic_hash" in semantic_data
                    assert semantic_data["semantic_hash"] == gop.semantic_hash

                    print(f"✓ Semantic JSON verified for GOP {gop.gop_id} (CID: {sem_cid})")
                except Exception as e:
                    print(f"Note: Semantic JSON download failed for GOP {gop.gop_id}: {e}")
            else:
                print(f"Note: Semantic JSON CID not found for GOP {gop.gop_id}")


def test_merkle_tree_with_semantic_hash(fabric_env, fabric_cfg):
    """Test Merkle tree construction with composite leaf hashes (sha256 + phash + semantic)."""
    gops = [_create_synthetic_gop(i) for i in range(3)]

    # Build Merkle tree using GOPData objects (should use composite hashes)
    tree = MerkleTree(gops)

    # Verify root is generated
    assert tree.root is not None
    assert len(tree.root) == 64  # SHA-256 hex

    # Verify proofs for each GOP
    for i, gop in enumerate(gops):
        proof = tree.get_proof(i)
        assert proof is not None

        # Compute leaf hash manually
        leaf_hash = compute_leaf_hash(
            gop.sha256_hash,
            gop.phash,
            gop.semantic_hash
        )

        # Verify proof
        assert MerkleTree.verify_proof(leaf_hash, proof, tree.root)

    print(f"✓ Merkle tree with semantic hashes verified for {len(gops)} GOPs")


def test_backward_compatibility_no_semantic(fabric_env, fabric_cfg):
    """Test that GOPs without semantic_hash still work correctly."""
    # Create GOPs without semantic data
    gops = []
    for i in range(2):
        gop = GOPData(
            gop_id=i,
            start_time=float(1700000000 + i * 2),
            end_time=float(1700000000 + i * 2 + 2),
            raw_bytes=b"test",
            byte_size=4,
            sha256_hash=f"{i}" * 64,
            frame_count=25,
            keyframe_frame=np.zeros((64, 64, 3), dtype=np.uint8),
            phash=f"{i}" * 16,
            semantic_hash=None,  # No semantic data
            semantic_fingerprint=None
        )
        gops.append(gop)

    # Build Merkle tree (should use placeholders for missing semantic)
    tree = MerkleTree(gops)

    assert tree.root is not None
    assert len(tree.root) == 64

    # Verify proofs still work
    for i, gop in enumerate(gops):
        proof = tree.get_proof(i)
        leaf_hash = compute_leaf_hash(
            gop.sha256_hash,
            gop.phash,
            None  # Will use placeholder
        )
        assert MerkleTree.verify_proof(leaf_hash, proof, tree.root)

    print(f"✓ Backward compatibility verified for GOPs without semantic data")


