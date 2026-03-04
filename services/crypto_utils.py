"""Cryptographic utilities for hashing and device signing."""
import base64
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple


def normalize_event_json_payload(raw_bytes: bytes) -> bytes:
    """Normalize event JSON by removing anchor metadata fields."""
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
        if isinstance(data, dict):
            data = dict(data)
            data.pop("_anchor", None)
            data.pop("_merkle", None)
            data.pop("evidence_hash", None)
            data.pop("evidence_hash_list", None)
        return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    except Exception:
        return raw_bytes


def compute_evidence_hash(json_bytes: bytes, img_bytes: Optional[bytes] = None) -> str:
    """Compute SHA256 hash of evidence content."""
    sha256 = hashlib.sha256()
    sha256.update(normalize_event_json_payload(json_bytes))
    if img_bytes:
        sha256.update(img_bytes)
    return sha256.hexdigest()


def build_batch_signature_payload(
    batch_id: str,
    camera_id: str,
    merkle_root: str,
    window_start: int,
    window_end: int,
    event_ids: List[str],
    event_hashes: List[str],
) -> bytes:
    """Build canonical JSON payload for batch signature."""
    payload = {
        "batchId": batch_id,
        "cameraId": camera_id,
        "merkleRoot": merkle_root,
        "windowStart": int(window_start),
        "windowEnd": int(window_end),
        "eventIds": event_ids,
        "eventHashes": event_hashes,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_payload_with_device_key(payload_bytes: bytes, key_path: Path, sign_algo: str) -> str:
    """Sign payload using device private key."""
    if sign_algo != "ECDSA_SHA256":
        raise RuntimeError(f"unsupported DEVICE_SIGN_ALGO: {sign_algo}")

    with tempfile.NamedTemporaryFile("wb", delete=False) as f:
        f.write(payload_bytes)
        payload_path = Path(f.name)

    try:
        cmd = ["openssl", "dgst", "-sha256", "-sign", str(key_path), "-binary", str(payload_path)]
        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode != 0:
            stderr = (proc.stderr or b"").decode("utf-8", errors="ignore").strip()
            raise RuntimeError(stderr or "openssl sign failed")
        return base64.b64encode(proc.stdout).decode("ascii")
    finally:
        try:
            payload_path.unlink(missing_ok=True)
        except Exception:
            pass


def auto_generate_device_material(camera_id: str) -> Tuple[Path, Path]:
    """Auto-generate device certificate and key if not exists."""
    base_dir = Path(tempfile.gettempdir()) / "cctv_device_autogen"
    base_dir.mkdir(parents=True, exist_ok=True)
    key_path = base_dir / f"{camera_id}.key.pem"
    cert_path = base_dir / f"{camera_id}.cert.pem"

    if key_path.exists() and cert_path.exists():
        return cert_path, key_path

    subj = f"/CN=device-{camera_id}@org1.example.com/O=Org1"
    cmd = [
        "openssl", "req", "-x509", "-newkey", "ec",
        "-pkeyopt", "ec_paramgen_curve:P-256", "-nodes",
        "-keyout", str(key_path), "-out", str(cert_path),
        "-days", "365", "-subj", subj,
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "failed to auto-generate device key/cert")
    return cert_path, key_path


def build_batch_signature_material(
    batch_id: str,
    camera_id: str,
    merkle_root: str,
    window_start: int,
    window_end: int,
    event_ids: List[str],
    event_hashes: List[str],
    device_cert_path: Path,
    device_key_path: Path,
    sign_algo: str,
    signature_required: bool,
) -> Tuple[str, str, str]:
    """Build complete signature material: cert PEM, signature, payload hash."""
    payload_bytes = build_batch_signature_payload(
        batch_id, camera_id, merkle_root,
        int(window_start), int(window_end),
        event_ids, event_hashes,
    )
    payload_hash = hashlib.sha256(payload_bytes).hexdigest()

    cert_path = device_cert_path
    key_path = device_key_path
    if not cert_path.exists() or not key_path.exists():
        if signature_required:
            raise RuntimeError(
                f"device cert/key not found: cert={cert_path}, key={key_path}; "
                "set DEVICE_CERT_PATH and DEVICE_KEY_PATH"
            )
        cert_path, key_path = auto_generate_device_material(camera_id)

    cert_pem = cert_path.read_text(encoding="utf-8").strip()
    signature_b64 = sign_payload_with_device_key(payload_bytes, key_path, sign_algo)
    return cert_pem, signature_b64, payload_hash
