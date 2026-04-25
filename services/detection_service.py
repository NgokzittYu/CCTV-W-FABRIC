"""Detection service for video stream processing and event handling."""
import base64
import hashlib
import json
import queue
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

import av
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
from services.ipfs_storage import VideoStorage
from services.merkle_utils import build_merkle_root_and_proofs
from services.gop_splitter import GOPSplitter, GOPData
from services.video_store import insert_video, insert_video_gops


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


class LatestFrameCapture:
    """Background capture that always keeps only the newest frame.

    This avoids OpenCV/video backend buffering a long backlog while YOLO
    inference is slower than the incoming stream. For live monitoring we
    prefer dropping stale frames over replaying old ones.
    """

    def __init__(self, source: str):
        self.source = source
        self.lock = threading.Lock()
        self.cond = threading.Condition(self.lock)
        self.frame = None
        self.frame_id = 0
        self.stopped = False
        self.fail_count = 0
        self.use_pyav = source.startswith(("http://", "https://", "rtsp://"))
        self.capture = self._open_capture()
        self.thread = threading.Thread(target=self._reader_loop, daemon=True)

    def _open_capture(self):
        if self.use_pyav:
            options = {
                "fflags": "nobuffer",
                "flags": "low_delay",
                "analyzeduration": "0",
                "probesize": "32768",
            }
            if self.source.startswith("rtsp://"):
                options["rtsp_transport"] = "tcp"
            return av.open(self.source, options=options)

        cap = cv2.VideoCapture(self.source)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        return cap

    def start(self):
        self.thread.start()

    def stop(self):
        with self.cond:
            self.stopped = True
            self.cond.notify_all()
        if self.capture:
            try:
                if self.use_pyav:
                    self.capture.close()
                else:
                    self.capture.release()
            except Exception:
                pass

    def _reconnect(self):
        try:
            if self.capture:
                if self.use_pyav:
                    self.capture.close()
                else:
                    self.capture.release()
        except Exception:
            pass
        time.sleep(0.5)
        self.capture = self._open_capture()
        self.fail_count = 0

    def _publish_frame(self, frame):
        with self.cond:
            self.frame = frame
            self.frame_id += 1
            self.cond.notify_all()

    def _reader_loop_cv2(self):
        while True:
            with self.lock:
                if self.stopped:
                    break

            success, frame = self.capture.read()
            if not success:
                self.fail_count += 1
                time.sleep(0.1)
                if self.fail_count >= 20:
                    print("[WARN] Stream read failed repeatedly, reconnecting...")
                    self._reconnect()
                continue

            self.fail_count = 0
            self._publish_frame(frame)

    def _reader_loop_pyav(self):
        while True:
            with self.lock:
                if self.stopped:
                    break

            try:
                video_stream = self.capture.streams.video[0]
                video_stream.thread_type = "AUTO"

                for frame in self.capture.decode(video=0):
                    with self.lock:
                        if self.stopped:
                            return
                    self.fail_count = 0
                    self._publish_frame(frame.to_ndarray(format="bgr24"))

                raise RuntimeError("stream ended")
            except Exception as e:
                self.fail_count += 1
                print(f"[WARN] Low-latency stream decode error: {e}")
                time.sleep(0.2)
                self._reconnect()

    def _reader_loop(self):
        if self.use_pyav:
            self._reader_loop_pyav()
            return
        self._reader_loop_cv2()

    def read_latest(self, last_frame_id: int, timeout: float = 1.0):
        """Return a new frame newer than ``last_frame_id`` if available."""
        deadline = time.time() + timeout
        with self.cond:
            while not self.stopped and self.frame_id == last_frame_id:
                remaining = deadline - time.time()
                if remaining <= 0:
                    return last_frame_id, None
                self.cond.wait(timeout=remaining)

            if self.stopped or self.frame is None:
                return last_frame_id, None

            return self.frame_id, self.frame.copy()


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
                [""] * len(event_ids),
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
                json.dumps([""] * len(event_ids), ensure_ascii=False),
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


class GOPAnchorManager:
    """Runs GOPSplitter on a live stream, stores GOP fingerprints, and anchors segments to Fabric.

    Every ``segment_gops`` GOPs, a segment is closed: Merkle tree built from
    GOP SHA-256+VIF leaf hashes, anchored to Fabric, and stored in video_store.db.
    """

    def __init__(self, stream_url: str, device_id: str, segment_gops: int = 30,
                 on_gop_callback=None, on_anchor_callback=None,
                 gop_build_queue_size: Optional[int] = None,
                 ingest_mode: str = "direct"):
        self.stream_url = stream_url
        self.device_id = device_id
        self.segment_gops = segment_gops
        self.on_gop_callback = on_gop_callback
        self.on_anchor_callback = on_anchor_callback
        self.gop_build_queue_size = gop_build_queue_size or SETTINGS.gop_build_queue_size
        self.ingest_mode = ingest_mode
        self.lock = threading.Lock()
        self._pending_gops: List[GOPData] = []
        self._segment_id: str = self._new_segment_id()
        self._splitter: Optional[GOPSplitter] = None
        self._anchor_queue: "queue.Queue[tuple[str, List[GOPData], float]]" = queue.Queue()
        self._anchor_worker: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_relative_end_time: Optional[float] = None
        self._last_mapped_end_time: Optional[float] = None

    def _new_segment_id(self) -> str:
        return f"live-{int(time.time())}-{uuid.uuid4().hex[:6]}"

    def start(self):
        self._stop_event.clear()
        self._last_relative_end_time = None
        self._last_mapped_end_time = None
        if not self._anchor_worker or not self._anchor_worker.is_alive():
            self._anchor_worker = threading.Thread(target=self._anchor_worker_loop, daemon=True)
            self._anchor_worker.start()
        self._splitter = GOPSplitter(
            self.stream_url,
            self._on_gop,
            queue_size=self.gop_build_queue_size,
            ingest_mode=self.ingest_mode,
        )
        self._splitter.start()
        print(f"[GOP_ANCHOR] Started for {self.stream_url}, segment every {self.segment_gops} GOPs")

    def stop(self):
        self._stop_event.set()
        if self._splitter:
            self._splitter.stop()

    def get_runtime_stats(self) -> Dict[str, Any]:
        stats: Dict[str, Any] = {
            "pending_gops": len(self._pending_gops),
            "segment_gops": self.segment_gops,
            "ingest_mode": self.ingest_mode,
        }
        if self._splitter:
            stats.update(self._splitter.get_runtime_stats())
        return stats

    def _anchor_worker_loop(self):
        while not self._stop_event.is_set():
            try:
                segment_id, gops, segment_closed_at = self._anchor_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._anchor_segment(segment_id, gops, segment_closed_at)
            finally:
                self._anchor_queue.task_done()

    def _on_gop(self, gop: GOPData):
        with self.lock:
            self._pending_gops.append(gop)
            count = len(self._pending_gops)

        print(f"[GOP_ANCHOR] GOP #{gop.gop_id} sha256={gop.sha256_hash[:16]}... vif={gop.vif[:16] if gop.vif else 'N/A'}... ({count}/{self.segment_gops})")

        # External callback hook (e.g. EIS evaluation)
        if self.on_gop_callback:
            try:
                self.on_gop_callback(gop)
            except Exception as e:
                print(f"[GOP_ANCHOR] on_gop_callback error: {e}")

        if count >= self.segment_gops:
            self._flush_segment()

    def _flush_segment(self):
        with self.lock:
            if not self._pending_gops:
                return
            gops = self._pending_gops[:]
            self._pending_gops.clear()
            segment_id = self._segment_id
            self._segment_id = self._new_segment_id()
            segment_closed_at = time.time()

        self._anchor_queue.put((segment_id, gops, segment_closed_at))

    def _compute_wallclock_bounds(self, gops: List[GOPData], segment_closed_at: float) -> List[Dict[str, float]]:
        """Project GOP-relative timestamps onto one continuous wall-clock timeline.

        GOP start/end times emitted by GOPSplitter are stream-PTS based and remain
        continuous across batches. The old implementation rebuilt a fresh mapping
        for every 5-GOP anchor batch, which inserted artificial multi-second gaps.
        Here we keep one offset for the whole live session and only rebase when
        the source PTS jumps backwards (for example after a reconnect/reset).
        """
        if not gops:
            return []
        first_rel_start = min(g.start_time for g in gops)
        last_rel_end = max(g.end_time for g in gops)
        should_rebase = (
            self._last_relative_end_time is None
            or self._last_mapped_end_time is None
            or first_rel_start < (self._last_relative_end_time - 1.0)
        )
        if should_rebase:
            # Anchor the end of the first observed batch to the current wall clock.
            offset = segment_closed_at - last_rel_end
        else:
            offset = self._last_mapped_end_time - self._last_relative_end_time
            projected_end = last_rel_end + offset
            if abs(projected_end - segment_closed_at) > 300:
                offset = segment_closed_at - last_rel_end
                should_rebase = True

        bounds = [
            {
                "start_time": g.start_time + offset,
                "end_time": g.end_time + offset,
            }
            for g in gops
        ]
        self._last_relative_end_time = last_rel_end
        self._last_mapped_end_time = last_rel_end + offset
        return bounds

    def _anchor_segment(self, segment_id: str, gops: List[GOPData], segment_closed_at: float):
        try:
            merkle_root, proofs = build_merkle_root_and_proofs(gops)
            wallclock_bounds = self._compute_wallclock_bounds(gops, segment_closed_at)
            mapped_segment_end = max(item["end_time"] for item in wallclock_bounds)

            batch_id = f"batch-{segment_id}"
            event_ids = [f"{segment_id}-gop{g.gop_id}" for g in gops]
            event_hashes = [g.sha256_hash for g in gops]
            event_vifs = [g.vif or "" for g in gops]
            window_start = int(min(item["start_time"] for item in wallclock_bounds))
            window_end = int(max(item["end_time"] for item in wallclock_bounds))

            fabric_samples = Path(SETTINGS.fabric_samples_path).expanduser().resolve()
            env, orderer_ca, org2_tls = build_fabric_env(fabric_samples)

            cert_pem, signature_b64, payload_hash = build_batch_signature_material(
                batch_id, self.device_id, merkle_root,
                window_start, window_end, event_ids, event_hashes,
                Path(SETTINGS.device_cert_path), Path(SETTINGS.device_key_path),
                SETTINGS.device_sign_algo, SETTINGS.device_signature_required,
                event_vifs=event_vifs,
            )

            tx_id = ""
            block_number = None
            try:
                result = invoke_chaincode(
                    env, orderer_ca, org2_tls,
                    SETTINGS.channel_name, SETTINGS.chaincode_name,
                    "CreateEvidenceBatch",
                    [batch_id, self.device_id, merkle_root, str(window_start), str(window_end),
                     json.dumps(event_ids), json.dumps(event_hashes),
                     json.dumps(event_vifs),
                     cert_pem, signature_b64, payload_hash],
                )
                tx_id = result.get("tx_id", "")
                block_number = get_latest_block_number(env, SETTINGS.channel_name)
            except Exception as e:
                print(f"[GOP_ANCHOR] Fabric anchor failed (non-fatal): {e}")
                tx_id = f"offline-{uuid.uuid4().hex[:8]}"

            # Persist raw GOPs into IPFS index so replay/verification can query them later.
            try:
                ipfs_storage = VideoStorage(
                    api_url=SETTINGS.ipfs_api_url,
                    gateway_url=SETTINGS.ipfs_gateway_url,
                    pin_enabled=SETTINGS.ipfs_pin_enabled,
                )
                for gop, bounds in zip(gops, wallclock_bounds):
                    ipfs_storage.upload_gop(
                        self.device_id,
                        gop,
                        timestamp_override=bounds["start_time"],
                        duration_override=max(bounds["end_time"] - bounds["start_time"], 0.0),
                    )
            except Exception as e:
                print(f"[GOP_ANCHOR] IPFS GOP upload failed (non-fatal): {e}")

            # Store in video_store.db
            total_bytes = sum(g.byte_size for g in gops)
            insert_video(
                video_id=segment_id, device_id=self.device_id,
                filename=f"live_{segment_id}.stream",
                file_size=total_bytes, gop_count=len(gops),
                merkle_root=merkle_root, tx_id=tx_id, block_number=block_number,
                created_at=mapped_segment_end,
            )
            insert_video_gops(segment_id, [
                {"video_id": segment_id, "gop_index": g.gop_id,
                 "sha256": g.sha256_hash, "vif": g.vif,
                 "start_time": bounds["start_time"], "end_time": bounds["end_time"],
                 "frame_count": g.frame_count, "byte_size": g.byte_size}
                for g, bounds in zip(gops, wallclock_bounds)
            ])

            print(f"[GOP_ANCHOR] Segment {segment_id} anchored: {len(gops)} GOPs, "
                  f"merkle={merkle_root[:16]}... tx={tx_id[:16]}... block={block_number}")

            # External callback hook (e.g. MAB feedback)
            if self.on_anchor_callback:
                try:
                    self.on_anchor_callback(segment_id, gops, {
                        "tx_id": tx_id,
                        "block_number": block_number,
                        "merkle_root": merkle_root,
                        "success": not tx_id.startswith("offline-"),
                    })
                except Exception as e:
                    print(f"[GOP_ANCHOR] on_anchor_callback error: {e}")

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[GOP_ANCHOR] Segment anchor failed: {e}")


def process_event_worker(
    event_data: Dict[str, Any],
    raw_snapshot: bytes,
    merkle_manager: Optional[MerkleBatchManager],
):
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

        if merkle_manager is not None:
            merkle_manager.add_event(event_data)
            print(f"[SAVE] event={event_id} hash={evidence_hash[:12]}... queued_for_merkle_batch")
        else:
            print(f"[SAVE] event={event_id} hash={evidence_hash[:12]}... evidence_only")

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
    merkle_manager: Optional[MerkleBatchManager],
    aggregate_config: Optional[Dict[str, Any]] = None,
    on_frame_callback=None,
):
    """Main detection loop for video stream processing."""
    source = resolve_stream_source(video_source)
    capture = LatestFrameCapture(source)
    capture.start()
    last_frame_id = 0

    agg_config = aggregate_config or {}
    aggregator = EventAggregator(
        min_frames=agg_config.get("min_frames", 3),
        max_missed_frames=agg_config.get("max_missed_frames", 5),
        iou_threshold=agg_config.get("iou_threshold", 0.3),
        window_seconds=agg_config.get("window_seconds", 10.0),
    )

    while True:
        last_frame_id, frame = capture.read_latest(last_frame_id, timeout=1.0)
        if frame is None:
            continue

        results = model.predict(
            frame,
            conf=confidence_threshold,
            classes=target_class_ids,
            imgsz=640,
            device=device,
            verbose=False,
        )[0]
        annotated_frame = results.plot()

        # External callback: expose YOLO results to EIS/MAB bridge
        if on_frame_callback:
            try:
                on_frame_callback(results.boxes, model.names, frame)
            except Exception:
                pass

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
