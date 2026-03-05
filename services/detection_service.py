"""Detection service for video stream processing and event handling."""
import base64
import hashlib
import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
from ultralytics import YOLO

from config import SETTINGS
from services.crypto_utils import (
    build_batch_signature_material,
    compute_evidence_hash,
    normalize_event_json_payload,
)
from services.event_aggregator import EventAggregator
from services.fabric_client import (
    build_fabric_env,
    get_latest_block_number,
    invoke_chaincode,
)
from services.merkle_utils import build_merkle_root_and_proofs


def resolve_stream_source(video_source: str) -> str:
    """Resolve video stream source (file path or RTSP URL)."""
    if video_source.startswith("rtsp://") or video_source.startswith("http://"):
        return video_source
    path = Path(video_source).expanduser().resolve()
    if path.exists():
        return str(path)
    return video_source


def build_event_id() -> str:
    """Generate unique event ID."""
    return f"event_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"


class MerkleBatchManager:
    """Manages batching of events for Merkle tree anchoring."""

    def __init__(self, window_seconds: int = 60):
        self.window_seconds = window_seconds
        self.lock = threading.Lock()
        self.pending_events: List[Dict[str, Any]] = []
        self.window_started_at: Optional[float] = None
        self.flush_thread = threading.Thread(target=self._flush_worker, daemon=True)
        self.flush_thread.start()

    def add_event(self, event_data: Dict[str, Any]):
        """Add event to pending batch."""
        with self.lock:
            if self.window_started_at is None:
                self.window_started_at = time.time()
            self.pending_events.append(event_data)

    def _flush_worker(self):
        """Background worker to flush batches periodically."""
        while True:
            time.sleep(5)
            self._try_flush()

    def _try_flush(self):
        """Try to flush pending batch if window expired."""
        with self.lock:
            if not self.pending_events:
                return
            if self.window_started_at is None:
                return
            elapsed = time.time() - self.window_started_at
            if elapsed < self.window_seconds:
                return

            batch = self.pending_events[:]
            self.pending_events.clear()
            self.window_started_at = None

        if batch:
            self._anchor_batch(batch)

    def _anchor_batch(self, batch: List[Dict[str, Any]]):
        """Anchor batch to Fabric with Merkle tree."""
        try:
            event_ids = [e["event_id"] for e in batch]
            event_hashes = [e.get("evidence_hash", "") for e in batch]
            window_start = int(min(e["timestamp"] for e in batch))
            window_end = int(max(e["timestamp"] for e in batch))

            merkle_root, proofs = build_merkle_root_and_proofs(event_hashes)
            batch_id = f"batch_{window_start}_{window_end}_{uuid.uuid4().hex[:6]}"

            fabric_samples = Path(SETTINGS.fabric_samples_path).expanduser().resolve()
            env, orderer_ca, org2_tls = build_fabric_env(fabric_samples)

            cert_pem, signature_b64, payload_hash = build_batch_signature_material(
                batch_id,
                SETTINGS.camera_id,
                merkle_root,
                window_start,
                window_end,
                event_ids,
                event_hashes,
                Path(SETTINGS.device_cert_path).expanduser().resolve(),
                Path(SETTINGS.device_key_path).expanduser().resolve(),
                SETTINGS.device_sign_algo,
                SETTINGS.device_signature_required,
            )

            args = [
                batch_id,
                SETTINGS.camera_id,
                merkle_root,
                str(window_start),
                str(window_end),
                json.dumps(event_ids, ensure_ascii=False),
                json.dumps(event_hashes, ensure_ascii=False),
                cert_pem,
                signature_b64,
                payload_hash,
            ]

            result = invoke_chaincode(
                env,
                orderer_ca,
                org2_tls,
                SETTINGS.channel_name,
                SETTINGS.chaincode_name,
                "CreateEvidenceBatch",
                args,
            )

            block_number = get_latest_block_number(env, SETTINGS.channel_name)
            tx_id = result.get("tx_id", "")

            for idx, event_data in enumerate(batch):
                event_id = event_data["event_id"]
                json_path = Path(SETTINGS.evidence_dir) / f"{event_id}.json"
                if json_path.exists():
                    try:
                        event_json = json.loads(json_path.read_text(encoding="utf-8"))
                        event_json["_merkle"] = {
                            "batchId": batch_id,
                            "windowStart": window_start,
                            "windowEnd": window_end,
                            "leafIndex": idx,
                            "proof": proofs[idx],
                            "proofLength": len(proofs[idx]),
                            "merkleRoot": merkle_root,
                            "batchSize": len(batch),
                            "txId": tx_id,
                            "blockNumber": block_number,
                            "timestamp": int(time.time()),
                        }
                        event_json["_anchor"] = {
                            "txId": tx_id,
                            "blockNumber": block_number,
                            "anchoredAt": int(time.time()),
                            "status": "Anchored",
                            "batchId": batch_id,
                        }
                        json_path.write_text(json.dumps(event_json, indent=2, ensure_ascii=False), encoding="utf-8")
                    except Exception as e:
                        print(f"[ERR] Failed to update receipt for {event_id}: {e}")

            # Save batch file
            try:
                from datetime import datetime
                batch_date = datetime.fromtimestamp(window_start).strftime("%Y-%m-%d")
                batch_dir = Path(SETTINGS.evidence_dir) / "batches" / batch_date
                batch_dir.mkdir(parents=True, exist_ok=True)

                batch_file = batch_dir / f"{batch_id}.json"
                batch_data = {
                    "batch_id": batch_id,
                    "camera_id": SETTINGS.camera_id,
                    "merkle_root": merkle_root,
                    "window_start": window_start,
                    "window_end": window_end,
                    "tx_id": tx_id,
                    "block_number": block_number,
                    "timestamp": int(time.time()),
                    "event_count": len(batch),
                    "events": [
                        {
                            "event_id": batch[i]["event_id"],
                            "evidence_hash": event_hashes[i],
                            "leaf_index": i,
                            "proof": proofs[i],
                        }
                        for i in range(len(batch))
                    ],
                }
                batch_file.write_text(json.dumps(batch_data, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"[BATCH] Saved batch file: {batch_file}")
            except Exception as e:
                print(f"[ERR] Failed to save batch file: {e}")

            print(f"[BATCH] Anchored batch={batch_id} events={len(batch)} tx={tx_id} block={block_number}")

        except Exception as e:
            print(f"[ERR] Batch anchor failed: {e}")


def process_event_worker(event_data: Dict[str, Any], raw_snapshot: bytes, merkle_manager: MerkleBatchManager):
    """Process completed event: save evidence and add to batch."""
    try:
        event_id = event_data["event_id"]
        evidence_dir = Path(SETTINGS.evidence_dir)
        evidence_dir.mkdir(parents=True, exist_ok=True)

        json_path = evidence_dir / f"{event_id}.json"
        img_path = evidence_dir / f"{event_id}.jpg"

        img_path.write_bytes(raw_snapshot)

        json_bytes = json.dumps(event_data, indent=2, ensure_ascii=False).encode("utf-8")
        evidence_hash = compute_evidence_hash(json_bytes, raw_snapshot)
        event_data["evidence_hash"] = evidence_hash
        event_data["evidence_hash_list"] = [evidence_hash]

        json_path.write_text(json.dumps(event_data, indent=2, ensure_ascii=False), encoding="utf-8")

        merkle_manager.add_event(event_data)

        print(f"[SAVE] event={event_id} hash={evidence_hash[:12]}...")

    except Exception as e:
        print(f"[ERR] process_event_worker failed: {e}")


def start_detection_loop(
    model: YOLO,
    video_source: str,
    confidence_threshold: float,
    target_class_ids: Optional[List[int]],
    device: str,
    frame_buffer: Dict[str, Optional[bytes]],
    lock: threading.Lock,
    merkle_manager: MerkleBatchManager,
    aggregate_config: Optional[Dict[str, Any]] = None,
):
    """Main detection loop for video stream processing."""
    source = resolve_stream_source(video_source)
    cap = cv2.VideoCapture(source)
    fail_count = 0

    agg_config = aggregate_config or {}
    aggregator = EventAggregator(
        min_frames=agg_config.get("min_frames", 3),
        max_missed_frames=agg_config.get("max_missed_frames", 5),
        iou_threshold=agg_config.get("iou_threshold", 0.3),
        window_seconds=agg_config.get("window_seconds", 10.0),
    )

    while True:
        success, frame = cap.read()
        if not success:
            fail_count += 1
            time.sleep(0.3)
            if fail_count >= 20:
                print("[WARN] Stream read failed repeatedly, reconnecting...")
                cap.release()
                source = resolve_stream_source(video_source)
                cap = cv2.VideoCapture(source)
                fail_count = 0
            continue

        fail_count = 0

        results = model.predict(
            frame,
            conf=confidence_threshold,
            classes=target_class_ids,
            imgsz=640,
            device=device,
            verbose=False,
        )[0]
        annotated_frame = results.plot()

        with lock:
            ret, buffer_raw = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            if ret:
                frame_buffer["raw"] = buffer_raw.tobytes()

            ret, buffer_ann = cv2.imencode(".jpg", annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
            if ret:
                frame_buffer["ann"] = buffer_ann.tobytes()

            raw_snapshot = frame_buffer["raw"]

        closed_events = aggregator.update(results.boxes, model.names)
        for event_data in closed_events:
            if raw_snapshot is None:
                continue
            print(
                f"[AGG] Closed event {event_data['event_id']} class={event_data['top_class']} "
                f"frames={event_data['frame_count']} duration={event_data['duration']}s"
            )
            t = threading.Thread(
                target=process_event_worker,
                args=(event_data, raw_snapshot, merkle_manager),
                daemon=True,
            )
            t.start()
