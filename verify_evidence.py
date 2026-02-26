#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import hashlib
import sys
from pathlib import Path


def run(cmd, env=None, check=True):
    proc = subprocess.run(cmd, env=env, text=True, capture_output=True)
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"Command failed ({proc.returncode}): {' '.join(cmd)}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc


def compute_evidence_hash(json_path: Path, image_path: Path) -> str:
    """Computes SHA256 hash of (normalized_json_bytes + image_bytes)."""
    sha256 = hashlib.sha256()

    with json_path.open("rb") as f:
        json_bytes = f.read()
    sha256.update(json_bytes)

    if image_path.exists():
        with image_path.open("rb") as f:
            image_bytes = f.read()
        sha256.update(image_bytes)
    
    return sha256.hexdigest()


def build_fabric_env(fabric_samples: Path):
    env = os.environ.copy()
    env["PATH"] = f"{fabric_samples / 'bin'}:{env.get('PATH', '')}"
    env["FABRIC_CFG_PATH"] = str(fabric_samples / 'config')

    env["CORE_PEER_TLS_ENABLED"] = "true"
    env["CORE_PEER_LOCALMSPID"] = "Org1MSP"
    env["CORE_PEER_ADDRESS"] = "localhost:7051"

    org1 = fabric_samples / "test-network" / "organizations" / "peerOrganizations" / "org1.example.com"
    env["CORE_PEER_TLS_ROOTCERT_FILE"] = str(
        org1 / "peers" / "peer0.org1.example.com" / "tls" / "ca.crt"
    )
    env["CORE_PEER_MSPCONFIGPATH"] = str(
        org1 / "users" / "Admin@org1.example.com" / "msp"
    )
    return env


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
    parser.add_argument("--evidence-dir", default="evidences", help="Directory containing event_*.json")
    parser.add_argument("--fabric-samples", default="../fabric-samples", help="Path to fabric-samples")
    parser.add_argument("--channel", default="mychannel", help="Fabric channel name")
    parser.add_argument("--chaincode", default="evidence", help="Chaincode name (default: evidence)")
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
    env = build_fabric_env(fabric_samples)
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
