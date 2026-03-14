"""Integration tests for GOP-level Merkle anchor on Fabric.

These tests require a running Fabric test-network with the evidence chaincode
deployed.  Set FABRIC_SAMPLES_PATH if the default ~/projects/fabric-samples
does not apply.

Run:
    python -m pytest tests/test_anchor_integration.py -v
"""
import hashlib
import json
import time
import uuid

import pytest

from services.fabric_client import (
    build_fabric_env,
    query_anchor,
    query_anchors_by_range,
    submit_anchor,
)
from services.merkle_utils import build_merkle_root_and_proofs
from config import SETTINGS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gop_hash(data: str) -> str:
    """Produce a deterministic 64-char hex hash from arbitrary string."""
    return hashlib.sha256(data.encode()).hexdigest()


def _unique_epoch_id(gateway: str = "gw_test") -> str:
    ts = int(time.time())
    return f"epoch_{gateway}_{ts}_{ts + 60}_{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def fabric_env():
    """Build Fabric environment once per test module."""
    from pathlib import Path
    fabric_samples = Path(SETTINGS.fabric_samples_path).expanduser().resolve()
    env, orderer_ca, org2_tls = build_fabric_env(fabric_samples)
    return env, orderer_ca, org2_tls


@pytest.fixture(scope="module")
def fabric_cfg():
    return SETTINGS.channel_name, SETTINGS.chaincode_name


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAnchorSubmitAndQuery:
    """End-to-end: build Merkle tree → submit anchor → query back."""

    def test_submit_and_query(self, fabric_env, fabric_cfg):
        env, orderer_ca, org2_tls = fabric_env
        channel, chaincode = fabric_cfg

        # 1. Simulate GOP hashes
        gop_hashes = [_gop_hash(f"gop_{i}") for i in range(8)]

        # 2. Build Merkle tree
        merkle_root, _proofs = build_merkle_root_and_proofs(gop_hashes)

        # 3. Submit anchor
        epoch_id = _unique_epoch_id()
        ts = str(int(time.time()))
        result = submit_anchor(
            env, orderer_ca, org2_tls,
            channel, chaincode,
            epoch_id, merkle_root, ts, device_count=1,
        )
        assert result["tx_id"], "submit_anchor should return a tx_id"

        # 4. Query anchor
        raw = query_anchor(env, channel, chaincode, epoch_id)
        record = json.loads(raw)
        assert record["merkleRoot"] == merkle_root
        assert record["epochId"] == epoch_id
        assert record["deviceCount"] == 1

    def test_duplicate_epoch_rejected(self, fabric_env, fabric_cfg):
        env, orderer_ca, org2_tls = fabric_env
        channel, chaincode = fabric_cfg

        gop_hashes = [_gop_hash(f"dup_{i}") for i in range(4)]
        merkle_root, _ = build_merkle_root_and_proofs(gop_hashes)

        epoch_id = _unique_epoch_id()
        ts = str(int(time.time()))
        submit_anchor(
            env, orderer_ca, org2_tls,
            channel, chaincode,
            epoch_id, merkle_root, ts, device_count=1,
        )

        # Second submit with same epoch_id should fail
        with pytest.raises(RuntimeError, match="already exists"):
            submit_anchor(
                env, orderer_ca, org2_tls,
                channel, chaincode,
                epoch_id, merkle_root, str(int(time.time())), device_count=1,
            )

    def test_timestamp_rollback_rejected(self, fabric_env, fabric_cfg):
        env, orderer_ca, org2_tls = fabric_env
        channel, chaincode = fabric_cfg

        gop_hashes = [_gop_hash(f"ts_{i}") for i in range(4)]
        merkle_root, _ = build_merkle_root_and_proofs(gop_hashes)

        now = int(time.time())
        epoch1 = _unique_epoch_id()
        submit_anchor(
            env, orderer_ca, org2_tls,
            channel, chaincode,
            epoch1, merkle_root, str(now), device_count=1,
        )

        # Submit with an older timestamp should fail
        epoch2 = _unique_epoch_id()
        with pytest.raises(RuntimeError, match="rollback"):
            submit_anchor(
                env, orderer_ca, org2_tls,
                channel, chaincode,
                epoch2, merkle_root, str(now - 100), device_count=1,
            )


class TestAnchorRangeQuery:
    """Test range queries over anchored records."""

    def test_range_query(self, fabric_env, fabric_cfg):
        env, orderer_ca, org2_tls = fabric_env
        channel, chaincode = fabric_cfg

        # Submit two anchors with a shared prefix
        prefix = f"epoch_range_{uuid.uuid4().hex[:6]}"
        now = int(time.time())

        for i in range(2):
            gop_hashes = [_gop_hash(f"range_{i}_{j}") for j in range(4)]
            merkle_root, _ = build_merkle_root_and_proofs(gop_hashes)
            eid = f"{prefix}_{now + i}_{now + i + 60}"
            submit_anchor(
                env, orderer_ca, org2_tls,
                channel, chaincode,
                eid, merkle_root, str(now + i), device_count=1,
            )

        # Range query
        start_key = f"anchor:{prefix}_"
        end_key = f"anchor:{prefix}_\uffff"
        raw = query_anchors_by_range(
            env, channel, chaincode, start_key, end_key,
        )
        records = json.loads(raw)
        assert len(records) >= 2
