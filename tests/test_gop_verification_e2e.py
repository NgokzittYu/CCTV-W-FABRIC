"""End-to-end integration tests for GOP verification.

These tests require:
1. Running Fabric test-network with evidence chaincode deployed
2. Running MinIO instance
3. Set FABRIC_SAMPLES_PATH if default ~/projects/fabric-samples doesn't apply

Run:
    python -m pytest tests/test_gop_verification_e2e.py -v -s
"""
import hashlib
import json
import time
import uuid
from pathlib import Path

import pytest

from services.fabric_client import build_fabric_env, submit_anchor
from services.gop_splitter import GOPData
from services.merkle_utils import MerkleTree
from services.minio_storage import VideoStorage
from services.gop_verifier import GOPVerifier
from config import SETTINGS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_synthetic_gop(gop_id: int, size: int = 1024) -> GOPData:
    """Create a synthetic GOP with deterministic content."""
    # Create synthetic H.264-like data (not real video, just for testing)
    content = f"GOP_{gop_id}_".encode() + b"\x00" * (size - len(f"GOP_{gop_id}_"))
    sha256_hash = hashlib.sha256(content).hexdigest()

    return GOPData(
        gop_id=gop_id,
        start_time=float(1700000000 + gop_id * 2),
        end_time=float(1700000000 + gop_id * 2 + 2),
        raw_bytes=content,
        byte_size=len(content),
        sha256_hash=sha256_hash,
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
def minio_storage():
    """Create MinIO storage instance."""
    storage = VideoStorage(
        endpoint=SETTINGS.minio_endpoint,
        access_key=SETTINGS.minio_access_key,
        secret_key=SETTINGS.minio_secret_key,
        bucket_name=SETTINGS.minio_bucket_name,
        secure=False,
    )
    return storage


@pytest.fixture(scope="module")
def gop_verifier(minio_storage, fabric_env, fabric_cfg):
    """Create GOP verifier instance."""
    env, orderer_ca, org2_tls = fabric_env
    channel, chaincode = fabric_cfg

    verifier = GOPVerifier(
        storage=minio_storage,
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
        self, minio_storage, fabric_env, fabric_cfg, gop_verifier
    ):
        """Test verification of intact GOP returns INTACT status."""
        env, orderer_ca, org2_tls = fabric_env
        channel, chaincode = fabric_cfg

        # 1. Create synthetic GOPs
        device_id = f"device_intact_{uuid.uuid4().hex[:8]}"
        gops = [_create_synthetic_gop(i, size=512) for i in range(4)]

        # 2. Upload GOPs to MinIO
        cids = []
        for gop in gops:
            cid = minio_storage.upload_gop(device_id, gop)
            cids.append(cid)

        # 3. Build Merkle tree
        tree = MerkleTree(cids)

        # 4. Upload Merkle tree JSON to MinIO
        epoch_id = _unique_epoch_id("intact")
        tree_filename = f"merkle_tree_{epoch_id}.json"
        minio_storage.upload_json(device_id, tree_filename, json.loads(tree.to_json()))

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
        self, minio_storage, fabric_env, fabric_cfg, gop_verifier
    ):
        """Test verification of tampered GOP returns NOT_INTACT status."""
        env, orderer_ca, org2_tls = fabric_env
        channel, chaincode = fabric_cfg

        # 1. Create synthetic GOPs
        device_id = f"device_tampered_{uuid.uuid4().hex[:8]}"
        gops = [_create_synthetic_gop(i, size=512) for i in range(4)]

        # 2. Upload GOPs to MinIO
        cids = []
        for gop in gops:
            cid = minio_storage.upload_gop(device_id, gop)
            cids.append(cid)

        # 3. Build Merkle tree
        tree = MerkleTree(cids)

        # 4. Upload Merkle tree JSON
        epoch_id = _unique_epoch_id("tampered")
        tree_filename = f"merkle_tree_{epoch_id}.json"
        minio_storage.upload_json(device_id, tree_filename, json.loads(tree.to_json()))

        # 5. Submit anchor to Fabric
        timestamp = str(int(time.time()))
        result = submit_anchor(
            env, orderer_ca, org2_tls,
            channel, chaincode,
            epoch_id, tree.root, timestamp, device_count=1,
        )
        assert result["tx_id"]

        # 6. Tamper with GOP[0] in MinIO
        tampered_content = b"TAMPERED_DATA" + b"\x00" * 499
        tampered_cid = hashlib.sha256(tampered_content).hexdigest()

        # Upload tampered GOP with original CID's path
        timestamp_int = int(gops[0].start_time)
        tampered_object_name = f"{device_id}/t_{timestamp_int}/{cids[0]}.h264"

        import io
        minio_storage.client.put_object(
            bucket_name=minio_storage.bucket,
            object_name=tampered_object_name,
            data=io.BytesIO(tampered_content),
            length=len(tampered_content),
            content_type="video/h264",
        )

        # 7. Verify GOP[0] - should be NOT_INTACT
        verification_result = gop_verifier.verify_gop(device_id, epoch_id, 0)

        assert verification_result["status"] == "NOT_INTACT", \
            f"Expected NOT_INTACT for tampered GOP, got {verification_result}"
        assert "reason" in verification_result

    def test_gop_verification_single_byte_tamper(
        self, minio_storage, fabric_env, fabric_cfg, gop_verifier
    ):
        """Test that even a single byte modification is detected."""
        env, orderer_ca, org2_tls = fabric_env
        channel, chaincode = fabric_cfg

        # 1. Create synthetic GOPs
        device_id = f"device_singlebyte_{uuid.uuid4().hex[:8]}"
        gops = [_create_synthetic_gop(i, size=512) for i in range(4)]

        # 2. Upload GOPs to MinIO
        cids = []
        for gop in gops:
            cid = minio_storage.upload_gop(device_id, gop)
            cids.append(cid)

        # 3. Build Merkle tree
        tree = MerkleTree(cids)

        # 4. Upload Merkle tree JSON
        epoch_id = _unique_epoch_id("singlebyte")
        tree_filename = f"merkle_tree_{epoch_id}.json"
        minio_storage.upload_json(device_id, tree_filename, json.loads(tree.to_json()))

        # 5. Submit anchor to Fabric
        timestamp = str(int(time.time()))
        result = submit_anchor(
            env, orderer_ca, org2_tls,
            channel, chaincode,
            epoch_id, tree.root, timestamp, device_count=1,
        )
        assert result["tx_id"]

        # 6. Download GOP[0], modify single byte, re-upload
        original_bytes = minio_storage.download_gop(device_id, cids[0])

        # Modify byte at position 100 (increment by 1)
        tampered_bytes = bytearray(original_bytes)
        tampered_bytes[100] = (tampered_bytes[100] + 1) % 256
        tampered_bytes = bytes(tampered_bytes)

        # Re-upload with same path
        timestamp_int = int(gops[0].start_time)
        object_name = f"{device_id}/t_{timestamp_int}/{cids[0]}.h264"

        import io
        minio_storage.client.put_object(
            bucket_name=minio_storage.bucket,
            object_name=object_name,
            data=io.BytesIO(tampered_bytes),
            length=len(tampered_bytes),
            content_type="video/h264",
        )

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
