#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import time
import hashlib
import re
from pathlib import Path
from collections import Counter

from config import SETTINGS


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
    """Computes SHA256 of evidence content, excluding local anchor metadata."""
    sha256 = hashlib.sha256()

    # 1. Read JSON and remove local-only receipt metadata.
    with json_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict):
        data = dict(data)
        data.pop("_anchor", None)
        data.pop("_merkle", None)
        data.pop("evidence_hash", None)
        data.pop("evidence_hash_list", None)
    normalized_json = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    sha256.update(normalized_json)

    # 2. READ Image if exists
    if image_path.exists():
        with image_path.open("rb") as f:
            image_bytes = f.read()
        sha256.update(image_bytes)
    
    return sha256.hexdigest()


def build_fabric_env(fabric_samples: Path):
    env = os.environ.copy()
    env["PATH"] = f"{fabric_samples / 'bin'}:{env.get('PATH', '')}"
    env["FABRIC_CFG_PATH"] = str(fabric_samples / 'config')

    env["CORE_PEER_TLS_ENABLED"] = SETTINGS.core_peer_tls_enabled
    env["CORE_PEER_LOCALMSPID"] = SETTINGS.core_peer_local_mspid
    env["CORE_PEER_ADDRESS"] = SETTINGS.core_peer_address

    org1 = (
        fabric_samples
        / "test-network"
        / "organizations"
        / "peerOrganizations"
        / SETTINGS.org1_domain
    )
    env["CORE_PEER_TLS_ROOTCERT_FILE"] = str(
        org1 / "peers" / f"peer0.{SETTINGS.org1_domain}" / "tls" / "ca.crt"
    )
    env["CORE_PEER_MSPCONFIGPATH"] = str(
        org1 / "users" / f"Admin@{SETTINGS.org1_domain}" / "msp"
    )

    orderer_ca = (
        fabric_samples
        / "test-network"
        / "organizations"
        / "ordererOrganizations"
        / SETTINGS.orderer_org_domain
        / "orderers"
        / SETTINGS.orderer_domain
        / "msp"
        / "tlscacerts"
        / f"tlsca.{SETTINGS.orderer_org_domain}-cert.pem"
    )
    org2_tls = (
        fabric_samples
        / "test-network"
        / "organizations"
        / "peerOrganizations"
        / SETTINGS.org2_domain
        / "peers"
        / f"peer0.{SETTINGS.org2_domain}"
        / "tls"
        / "ca.crt"
    )

    return env, orderer_ca, org2_tls


def prepare_evidence_args(json_path: Path, camera_id: str):
    with json_path.open("r", encoding="utf-8") as f:
        event = json.load(f)

    event_id = str(event.get("event_id", "")).strip()
    if not event_id:
        raise ValueError(f"event_id missing in {json_path}")
    
    detections = event.get("detections", [])
    obj_count = len(detections)
    
    # Determine Event Type based on labels (simple logic for MVP)
    labels = [d.get("class", "unknown") for d in detections]
    top_class = Counter(labels).most_common(1)[0][0] if labels else "unknown"
    event_type = f"detection_{top_class}"

    # Compute Hash
    # Assuming image has same basename but .jpg
    image_path = json_path.with_suffix(".jpg")
    evidence_hash = compute_evidence_hash(json_path, image_path)

    # rawDataUrl - allow constructing a local file URL or just filename for now
    raw_data_url = f"file://{json_path.name}"

    # CreateEvidence(id, cameraId, eventType, objectCount, evidenceHash, rawDataUrl)
    args = [
        event_id,
        camera_id,
        event_type,
        str(obj_count),
        evidence_hash,
        raw_data_url
    ]
    return event_id, args


def evidence_exists(env, channel, chaincode, evidence_id):
    # Query function: EvidenceExists(id) -> bool
    # But often checking ReadEvidence is easier if EvidenceExists isn't exposed directly or returns error.
    # Our chaincode HAS EvidenceExists.
    cmd = [
        "peer",
        "chaincode",
        "query",
        "-C",
        channel,
        "-n",
        chaincode,
        "-c",
        json.dumps({"function": "EvidenceExists", "Args": [evidence_id]}),
    ]
    proc = subprocess.run(cmd, env=env, text=True, capture_output=True)
    # If successful, output should be "true" or "false"
    if proc.returncode == 0:
        return "true" in proc.stdout.lower()
    return False


def invoke_chaincode(env, orderer_ca, org2_tls, channel, chaincode, function_name, args):
    payload = json.dumps({"function": function_name, "Args": args})
    cmd = [
        "peer",
        "chaincode",
        "invoke",
        "-o",
        SETTINGS.orderer_address,
        "--ordererTLSHostnameOverride",
        SETTINGS.orderer_tls_hostname_override,
        "--tls",
        "--cafile",
        str(orderer_ca),
        "-C",
        channel,
        "-n",
        chaincode,
        "--peerAddresses",
        SETTINGS.org1_peer_address,
        "--tlsRootCertFiles",
        env["CORE_PEER_TLS_ROOTCERT_FILE"],
        "--peerAddresses",
        SETTINGS.org2_peer_address,
        "--tlsRootCertFiles",
        str(org2_tls),
        "--waitForEvent",
        "--waitForEventTimeout",
        "30s",
        "-c",
        payload,
    ]
    proc = run(cmd, env=env, check=True)

    tx_id = ""
    # Fabric CLI typically writes txid in stderr:
    # "... txid [<hex>] committed with status (VALID) ..."
    tx_match = re.search(r"txid \[([0-9a-fA-F]+)\]", proc.stderr or "")
    if tx_match:
        tx_id = tx_match.group(1)

    return {"tx_id": tx_id, "stdout": proc.stdout, "stderr": proc.stderr}


def invoke_create_evidence(env, orderer_ca, org2_tls, channel, chaincode, args):
    return invoke_chaincode(env, orderer_ca, org2_tls, channel, chaincode, "CreateEvidence", args)


def get_latest_block_number(env, channel):
    cmd = ["peer", "channel", "getinfo", "-c", channel]
    proc = subprocess.run(cmd, env=env, text=True, capture_output=True)
    if proc.returncode != 0:
        return None

    # Output format:
    # "Blockchain info: {\"height\":15,...}"
    out = (proc.stdout or "").strip()
    if "Blockchain info:" not in out:
        return None
    try:
        payload = out.split("Blockchain info:", 1)[1].strip()
        info = json.loads(payload)
        height = int(info.get("height", 0))
        if height <= 0:
            return None
        return height - 1
    except Exception:
        return None


def write_anchor_receipt(json_path: Path, tx_id: str, block_number):
    try:
        with json_path.open("r", encoding="utf-8") as f:
            event = json.load(f)
    except Exception:
        return

    event["_anchor"] = {
        "txId": tx_id or "",
        "blockNumber": block_number,
        "anchoredAt": int(time.time()),
    }

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(event, f, indent=2, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="Anchor YOLO evidence to Hyperledger Fabric with Hashing")
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
    parser.add_argument("--camera-id", default=SETTINGS.camera_id, help="Camera ID")
    parser.add_argument("--limit", type=int, default=0, help="Max files to process (0 = all)")
    parser.add_argument("--dry-run", action="store_true", help="Print mapped args without invoking")
    args = parser.parse_args()

    fabric_samples = Path(args.fabric_samples).resolve()
    evidence_dir = Path(args.evidence_dir).resolve()

    if not evidence_dir.exists():
        raise FileNotFoundError(f"evidence-dir not found: {evidence_dir}")

    env, orderer_ca, org2_tls = build_fabric_env(fabric_samples)

    files = sorted(evidence_dir.glob("event_*.json"))
    if args.limit > 0:
        files = files[: args.limit]

    if not files:
        print(f"No event JSON found under: {evidence_dir}")
        return

    print(f"Target Chaincode: {args.chaincode}")
    print(f"Processing {len(files)} files...")

    created = 0
    skipped = 0

    for fp in files:
        try:
            event_id, func_args = prepare_evidence_args(fp, args.camera_id)
        except Exception as e:
            print(f"[ERR] Failed to prepare {fp.name}: {e}")
            continue

        if args.dry_run:
            print(f"[DRY] {event_id} -> Hash: {func_args[4]} | Args: {func_args}")
            continue

        if evidence_exists(env, args.channel, args.chaincode, event_id):
            skipped += 1
            print(f"[SKIP] {event_id} already exists on chain.")
            continue

        try:
            invoke_res = invoke_create_evidence(
                env, orderer_ca, org2_tls, args.channel, args.chaincode, func_args
            )
            block_number = get_latest_block_number(env, args.channel)
            write_anchor_receipt(fp, invoke_res.get("tx_id", ""), block_number)
            created += 1
            print(
                f"[OK]   {event_id} anchored. "
                f"txId={invoke_res.get('tx_id', '') or 'N/A'} block={block_number}"
            )
        except Exception as e:
            print(f"[FAIL] {event_id} invoke error: {e}")

    print(f"Done. Anchored={created}, Skipped={skipped}, Total={len(files)}")


if __name__ == "__main__":
    main()
