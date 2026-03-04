"""Tests for cryptographic utilities."""
import json
from pathlib import Path
from services.crypto_utils import (
    normalize_event_json_payload,
    compute_evidence_hash,
    build_batch_signature_payload,
)


def test_normalize_event_json_payload():
    """Test JSON normalization removes anchor metadata."""
    data = {
        "event_id": "test123",
        "timestamp": 1234567890,
        "_anchor": {"txId": "abc"},
        "_merkle": {"root": "xyz"},
        "evidence_hash": "hash123",
    }
    raw_bytes = json.dumps(data).encode("utf-8")
    normalized = normalize_event_json_payload(raw_bytes)
    result = json.loads(normalized.decode("utf-8"))

    assert "event_id" in result
    assert "_anchor" not in result
    assert "_merkle" not in result
    assert "evidence_hash" not in result


def test_compute_evidence_hash():
    """Test evidence hash computation."""
    json_bytes = b'{"event_id": "test123"}'
    img_bytes = b"fake image data"

    hash1 = compute_evidence_hash(json_bytes, img_bytes)
    hash2 = compute_evidence_hash(json_bytes, img_bytes)

    assert hash1 == hash2
    assert len(hash1) == 64


def test_build_batch_signature_payload():
    """Test batch signature payload construction."""
    payload = build_batch_signature_payload(
        batch_id="batch123",
        camera_id="cam001",
        merkle_root="a" * 64,
        window_start=1000,
        window_end=2000,
        event_ids=["e1", "e2"],
        event_hashes=["h1", "h2"],
    )

    assert isinstance(payload, bytes)
    data = json.loads(payload.decode("utf-8"))
    assert data["batchId"] == "batch123"
    assert data["cameraId"] == "cam001"
    assert len(data["eventIds"]) == 2
