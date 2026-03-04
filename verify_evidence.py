#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
from pathlib import Path

from config import SETTINGS
from services.crypto_utils import compute_evidence_hash as _compute_hash_from_bytes
from services.fabric_client import build_fabric_env


def compute_evidence_hash(json_path: Path, image_path: Path) -> str:
    """Computes SHA256 hash of (normalized_json_bytes + image_bytes)."""
    json_bytes = json_path.read_bytes()
    img_bytes = image_path.read_bytes() if image_path.exists() else None
    return _compute_hash_from_bytes(json_bytes, img_bytes)


def get_onchain_evidence(env, channel, chaincode, evidence_id):
    cmd = [
        "peer",
        "chaincode",
        "query",
        "-C",
        channel,
        "-n",
        chaincode,
        "-c",
        json.dumps({"function": "ReadEvidence", "Args": [evidence_id]}),
    ]
    proc = subprocess.run(cmd, env=env, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Failed to query evidence {evidence_id}: {proc.stderr}")
    
    return json.loads(proc.stdout)


def main():
    parser = argparse.ArgumentParser(description="Verify local evidence against on-chain hash")
    parser.add_argument("evidence_id", help="The ID to verify (e.g., event_0055)")
    parser.add_argument(
        "--evidence-dir",
        default=str(SETTINGS.evidence_dir),
        help="Directory containing event_*.json",
    )
    parser.add_argument(
        "--fabric-samples",
        default=str(SETTINGS.fabric_samples_path),
        help="Path to fabric-samples",
    )
    parser.add_argument("--channel", default=SETTINGS.channel_name, help="Fabric channel name")
    parser.add_argument(
        "--chaincode",
        default=SETTINGS.chaincode_name,
        help="Chaincode name (default: evidence)",
    )
    args = parser.parse_args()

    fabric_samples = Path(args.fabric_samples).resolve()
    evidence_dir = Path(args.evidence_dir).resolve()
    
    # 1. Locate local files
    json_path = evidence_dir / f"{args.evidence_id}.json"
    img_path = evidence_dir / f"{args.evidence_id}.jpg"

    if not json_path.exists():
        print(f"[ERR] Local file not found: {json_path}")
        sys.exit(1)

    # 2. Compute Local Hash
    print(f"Computing local hash for {args.evidence_id}...")
    local_hash = compute_evidence_hash(json_path, img_path)
    print(f"Local Hash:   {local_hash}")

    # 3. Fetch On-Chain Data
    env, _, _ = build_fabric_env(fabric_samples)
    try:
        onchain_data = get_onchain_evidence(env, args.channel, args.chaincode, args.evidence_id)
    except Exception as e:
        print(f"[ERR] Could not fetch from blockchain: {e}")
        sys.exit(1)

    remote_hash = onchain_data.get("evidenceHash", "")
    print(f"On-Chain Hash: {remote_hash}")

    # 4. Compare
    if local_hash == remote_hash:
        print("\n✅ VERIFICATION SUCCESS: content matches the immutable record.")
    else:
        print("\n❌ VERIFICATION FAILED: local content has been tampered with or differs from chain.")
        sys.exit(1)


if __name__ == "__main__":
    main()
