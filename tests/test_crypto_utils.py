import json

import pytest

from services.crypto_utils import (
    build_batch_signature_payload,
    compute_evidence_hash,
    normalize_event_json_payload,
)


pytestmark = pytest.mark.unit


def test_normalize_event_json_payload_removes_derived_metadata():
    payload = {
        "event_id": "evt-1",
        "camera_id": "cam-1",
        "_anchor": {"tx_id": "abc"},
        "_merkle": {"root": "def"},
        "evidence_hash": "derived",
    }

    normalized = normalize_event_json_payload(json.dumps(payload).encode("utf-8"))
    result = json.loads(normalized.decode("utf-8"))

    assert result == {"camera_id": "cam-1", "event_id": "evt-1"}


def test_compute_evidence_hash_is_stable_and_image_sensitive():
    json_bytes = b'{"event_id":"evt-1"}'

    first = compute_evidence_hash(json_bytes, b"image-a")
    second = compute_evidence_hash(json_bytes, b"image-a")
    third = compute_evidence_hash(json_bytes, b"image-b")

    assert first == second
    assert first != third
    assert len(first) == 64


def test_build_batch_signature_payload_is_canonical():
    payload = build_batch_signature_payload(
        batch_id="batch-1",
        camera_id="cam-1",
        merkle_root="a" * 64,
        window_start=1.0,
        window_end=2.0,
        event_ids=["evt-1", "evt-2"],
        event_hashes=["h1", "h2"],
    )

    result = json.loads(payload.decode("utf-8"))

    assert result["batchId"] == "batch-1"
    assert result["cameraId"] == "cam-1"
    assert result["merkleRoot"] == "a" * 64
    assert result["eventIds"] == ["evt-1", "evt-2"]
