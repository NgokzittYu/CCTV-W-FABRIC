#!/usr/bin/env python3
import argparse
import base64
import hashlib
import json
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import SETTINGS
from services.crypto_utils import compute_evidence_hash as compute_hash_from_bytes, normalize_event_json_payload
from services.fabric_client import (
    build_fabric_env,
    evidence_exists,
    get_latest_block_number,
    invoke_chaincode,
    query_chaincode,
    run,
)
from services.merkle_utils import build_merkle_root_and_proofs, sha256_digest
from services.crypto_utils import build_batch_signature_material


@dataclass
class EvidenceItem:
    event_id: str
    event_type: str
    object_count: int
    evidence_hash: str
    timestamp: int
    json_path: Path
    image_path: Path


def compute_evidence_hash(json_path: Path, image_path: Path) -> str:
    """Computes SHA256 of evidence content, excluding local anchor metadata."""
    json_bytes = json_path.read_bytes()
    img_bytes = image_path.read_bytes() if image_path.exists() else None
    return compute_hash_from_bytes(json_bytes, img_bytes)


def parse_event_item(json_path: Path, camera_id: str) -> EvidenceItem:
    with json_path.open("r", encoding="utf-8") as f:
        event = json.load(f)

    event_id = str(event.get("event_id", "")).strip()
    if not event_id:
        raise ValueError(f"event_id missing in {json_path}")

    detections = event.get("detections", [])
    object_count = len(detections)
    labels = [d.get("class", "unknown") for d in detections]
    top_class = Counter(labels).most_common(1)[0][0] if labels else "unknown"
    event_type = f"detection_{top_class}"

    image_path = json_path.with_suffix(".jpg")
    evidence_hash = compute_evidence_hash(json_path, image_path)

    ts_raw = event.get("timestamp", int(json_path.stat().st_mtime))
    try:
        timestamp = int(ts_raw)
    except Exception:
        timestamp = int(json_path.stat().st_mtime)

    return EvidenceItem(
        event_id=event_id,
        event_type=event_type,
        object_count=object_count,
        evidence_hash=evidence_hash,
        timestamp=timestamp,
        json_path=json_path,
        image_path=image_path,
    )


def invoke_create_evidence(
    env: Dict[str, str],
    orderer_ca: Path,
    org2_tls: Path,
    channel: str,
    chaincode: str,
    item: EvidenceItem,
    camera_id: str,
) -> Dict[str, str]:
    args = [
        item.event_id,
        camera_id,
        item.event_type,
        str(item.object_count),
        item.evidence_hash,
        f"file://{item.json_path.name}",
    ]
    return invoke_chaincode(env, orderer_ca, org2_tls, channel, chaincode, "CreateEvidence", args)


def invoke_create_evidence_batch(
    env: Dict[str, str],
    orderer_ca: Path,
    org2_tls: Path,
    channel: str,
    chaincode: str,
    batch_id: str,
    camera_id: str,
    merkle_root: str,
    window_start: int,
    window_end: int,
    event_ids: List[str],
    event_hashes: List[str],
    device_cert_pem: str,
    signature_b64: str,
    payload_hash_hex: str,
) -> Dict[str, str]:
    args = [
        batch_id,
        camera_id,
        merkle_root,
        str(int(window_start)),
        str(int(window_end)),
        json.dumps(event_ids, ensure_ascii=False),
        json.dumps(event_hashes, ensure_ascii=False),
        device_cert_pem,
        signature_b64,
        payload_hash_hex,
    ]
    return invoke_chaincode(env, orderer_ca, org2_tls, channel, chaincode, "CreateEvidenceBatch", args)


def invoke_put_private_evidence(
    env: Dict[str, str],
    orderer_ca: Path,
    org2_tls: Path,
    channel: str,
    chaincode: str,
    item: EvidenceItem,
    use_transient: bool,
) -> Dict[str, str]:
    if not item.image_path.exists():
        raise RuntimeError(f"image not found for {item.event_id}: {item.image_path}")

    image_bytes = item.image_path.read_bytes()
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    image_sha = hashlib.sha256(image_bytes).hexdigest()
    mime_type = "image/jpeg"

    transient_map = None
    if use_transient:
        args = [item.event_id, "", mime_type, image_sha]
        transient_map = {
            "rawEvidence": {
                "imageBase64": image_b64,
                "mimeType": mime_type,
                "imageSHA256": image_sha,
            }
        }
    else:
        args = [item.event_id, image_b64, mime_type, image_sha]

    return invoke_chaincode(
        env,
        orderer_ca,
        org2_tls,
        channel,
        chaincode,
        "PutRawEvidencePrivate",
        args,
        transient_map=transient_map,
    )


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def write_single_anchor_receipt(json_path: Path, tx_id: str, block_number: Optional[int]) -> None:
    try:
        event = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:
        return

    event["_anchor"] = {
        "txId": tx_id or "",
        "blockNumber": block_number,
        "anchoredAt": int(time.time()),
        "status": "Anchored",
    }
    write_json(json_path, event)


def write_batch_receipts(
    items: List[EvidenceItem],
    proofs: List[List[Dict[str, str]]],
    batch_id: str,
    merkle_root: str,
    window_start: int,
    window_end: int,
    tx_id: str,
    block_number: Optional[int],
) -> None:
    anchored_at = int(time.time())
    for idx, item in enumerate(items):
        try:
            event_data = json.loads(item.json_path.read_text(encoding="utf-8"))
        except Exception:
            event_data = {"event_id": item.event_id}

        event_data["evidence_hash_list"] = [item.evidence_hash]
        event_data["_merkle"] = {
            "batchId": batch_id,
            "windowStart": int(window_start),
            "windowEnd": int(window_end),
            "leafIndex": idx,
            "proof": proofs[idx],
            "proofLength": len(proofs[idx]),
            "merkleRoot": merkle_root,
            "batchSize": len(items),
        }
        event_data["_anchor"] = {
            "txId": tx_id,
            "blockNumber": block_number,
            "anchoredAt": anchored_at,
            "status": "Anchored",
            "batchId": batch_id,
        }
        write_json(item.json_path, event_data)


def chunked(items: List[EvidenceItem], batch_size: int) -> List[List[EvidenceItem]]:
    if batch_size <= 0:
        return [items]
    out: List[List[EvidenceItem]] = []
    for idx in range(0, len(items), batch_size):
        out.append(items[idx : idx + batch_size])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Anchor YOLO evidences to Hyperledger Fabric (single or signed batch mode)"
    )
    parser.add_argument("--evidence-dir", default=str(SETTINGS.evidence_dir), help="Directory containing event_*.json")
    parser.add_argument("--fabric-samples", default=str(SETTINGS.fabric_samples_path), help="Path to fabric-samples")
    parser.add_argument("--channel", default=SETTINGS.channel_name, help="Fabric channel name")
    parser.add_argument("--chaincode", default=SETTINGS.chaincode_name, help="Chaincode name")
    parser.add_argument("--camera-id", default=SETTINGS.camera_id, help="Camera ID")
    parser.add_argument("--limit", type=int, default=0, help="Max files to process (0 = all)")
    parser.add_argument("--dry-run", action="store_true", help="Only print planned operations")

    parser.add_argument(
        "--mode",
        choices=["single", "batch"],
        default="single",
        help="single=CreateEvidence per event, batch=CreateEvidenceBatch with device signature",
    )
    parser.add_argument("--batch-size", type=int, default=20, help="Batch size in batch mode")
    parser.add_argument("--batch-id-prefix", default="batch_offline", help="Batch ID prefix in batch mode")

    parser.add_argument("--put-private", action="store_true", help="Also write raw image to PDC via PutRawEvidencePrivate")
    parser.add_argument(
        "--private-use-transient",
        action="store_true",
        help="When --put-private is enabled, send raw image in transient map",
    )

    parser.add_argument("--device-cert-path", default=str(SETTINGS.device_cert_path), help="Device cert PEM path")
    parser.add_argument("--device-key-path", default=str(SETTINGS.device_key_path), help="Device private key PEM path")
    parser.add_argument("--device-sign-algo", default=SETTINGS.device_sign_algo, help="Device signing algorithm")
    parser.add_argument(
        "--device-signature-required",
        action=argparse.BooleanOptionalAction,
        default=SETTINGS.device_signature_required,
        help="Require pre-existing device key/cert for signed batch",
    )
    parser.add_argument(
        "--export-audit-batch",
        default="",
        help="Only run ExportAuditTrail(batchID) and print JSON result",
    )

    args = parser.parse_args()

    fabric_samples = Path(args.fabric_samples).expanduser().resolve()
    evidence_dir = Path(args.evidence_dir).expanduser().resolve()
    device_cert_path = Path(args.device_cert_path).expanduser().resolve()
    device_key_path = Path(args.device_key_path).expanduser().resolve()

    if not evidence_dir.exists():
        raise FileNotFoundError(f"evidence-dir not found: {evidence_dir}")

    env, orderer_ca, org2_tls = build_fabric_env(fabric_samples)

    if args.export_audit_batch:
        output = query_chaincode(
            env,
            args.channel,
            args.chaincode,
            "ExportAuditTrail",
            [args.export_audit_batch],
        )
        print(output)
        return

    files = sorted(evidence_dir.glob("event_*.json"))
    if args.limit > 0:
        files = files[: args.limit]

    if not files:
        print(f"No event JSON found under: {evidence_dir}")
        return

    items: List[EvidenceItem] = []
    for fp in files:
        try:
            items.append(parse_event_item(fp, args.camera_id))
        except Exception as exc:
            print(f"[ERR] skip {fp.name}: {exc}")

    if not items:
        print("No valid event files to process.")
        return

    print(f"Target chaincode: {args.chaincode}")
    print(f"Mode={args.mode} | Files={len(items)}")

    existing_ids = set()
    for item in items:
        if evidence_exists(env, args.channel, args.chaincode, item.event_id):
            existing_ids.add(item.event_id)

    pending_items = [item for item in items if item.event_id not in existing_ids]
    if existing_ids:
        print(f"[INFO] Existing on-chain items skipped: {len(existing_ids)}")

    if not pending_items:
        print("Nothing to anchor.")
        return

    anchored = 0
    private_written = 0

    if args.mode == "single":
        for item in pending_items:
            if args.dry_run:
                print(f"[DRY] CreateEvidence event={item.event_id} hash={item.evidence_hash}")
                if args.put_private:
                    print(
                        f"[DRY] PutRawEvidencePrivate event={item.event_id} transient={str(args.private_use_transient).lower()}"
                    )
                continue

            try:
                invoke_res = invoke_create_evidence(
                    env,
                    orderer_ca,
                    org2_tls,
                    args.channel,
                    args.chaincode,
                    item,
                    args.camera_id,
                )
                block_number = get_latest_block_number(env, args.channel)
                write_single_anchor_receipt(item.json_path, invoke_res.get("tx_id", ""), block_number)
                anchored += 1
                print(
                    f"[OK] event={item.event_id} tx={invoke_res.get('tx_id', '') or 'N/A'} block={block_number}"
                )

                if args.put_private:
                    invoke_put_private_evidence(
                        env,
                        orderer_ca,
                        org2_tls,
                        args.channel,
                        args.chaincode,
                        item,
                        use_transient=args.private_use_transient,
                    )
                    private_written += 1
                    print(
                        f"[OK] private raw saved event={item.event_id} transient={str(args.private_use_transient).lower()}"
                    )
            except Exception as exc:
                print(f"[FAIL] event={item.event_id} error={exc}")
    else:
        batches = chunked(pending_items, args.batch_size)
        for group in batches:
            event_ids = [x.event_id for x in group]
            event_hashes = [x.evidence_hash for x in group]
            window_start = min(x.timestamp for x in group)
            window_end = max(x.timestamp for x in group)
            merkle_root, proofs = build_merkle_root_and_proofs(event_hashes)
            batch_id = f"{args.batch_id_prefix}_{window_start}_{window_end}_{uuid.uuid4().hex[:6]}"

            if args.dry_run:
                print(
                    f"[DRY] CreateEvidenceBatch batch={batch_id} events={len(group)} root={merkle_root[:12]}..."
                )
                if args.put_private:
                    for item in group:
                        print(
                            f"[DRY] PutRawEvidencePrivate event={item.event_id} transient={str(args.private_use_transient).lower()}"
                        )
                continue

            try:
                cert_pem, signature_b64, payload_hash_hex = build_batch_signature_material(
                    batch_id,
                    args.camera_id,
                    merkle_root,
                    window_start,
                    window_end,
                    event_ids,
                    event_hashes,
                    device_cert_path=device_cert_path,
                    device_key_path=device_key_path,
                    sign_algo=args.device_sign_algo,
                    signature_required=args.device_signature_required,
                )
                invoke_res = invoke_create_evidence_batch(
                    env,
                    orderer_ca,
                    org2_tls,
                    args.channel,
                    args.chaincode,
                    batch_id,
                    args.camera_id,
                    merkle_root,
                    window_start,
                    window_end,
                    event_ids,
                    event_hashes,
                    cert_pem,
                    signature_b64,
                    payload_hash_hex,
                )
                block_number = get_latest_block_number(env, args.channel)
                write_batch_receipts(
                    group,
                    proofs,
                    batch_id,
                    merkle_root,
                    window_start,
                    window_end,
                    invoke_res.get("tx_id", ""),
                    block_number,
                )
                anchored += len(group)
                print(
                    f"[OK] batch={batch_id} events={len(group)} tx={invoke_res.get('tx_id', '') or 'N/A'} block={block_number}"
                )

                if args.put_private:
                    for item in group:
                        invoke_put_private_evidence(
                            env,
                            orderer_ca,
                            org2_tls,
                            args.channel,
                            args.chaincode,
                            item,
                            use_transient=args.private_use_transient,
                        )
                        private_written += 1
                    print(
                        f"[OK] private raw saved for batch={batch_id} count={len(group)} transient={str(args.private_use_transient).lower()}"
                    )
            except Exception as exc:
                print(f"[FAIL] batch={batch_id} error={exc}")

    print(
        f"Done. Total={len(items)} Existing={len(existing_ids)} Anchored={anchored} "
        f"PrivateWritten={private_written}"
    )


if __name__ == "__main__":
    main()
