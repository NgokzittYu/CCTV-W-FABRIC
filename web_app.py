import asyncio
import hashlib
import json
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import torch
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from ultralytics import YOLO

# Reuse Fabric helpers from anchor_to_fabric.py
from anchor_to_fabric import build_fabric_env, invoke_chaincode

# Configuration
FABRIC_SAMPLES_PATH = Path.home() / "projects" / "fabric-samples"
EVIDENCE_DIR = Path("evidences").resolve()
CAMERA_ID = "cctv-kctmc-apple-01"
CHAINCODE_NAME = "evidence"
CHANNEL_NAME = "mychannel"

# Event aggregation config
AGGREGATE_MIN_FRAMES = 3
AGGREGATE_MAX_MISSED_FRAMES = 6
AGGREGATE_IOU_THRESHOLD = 0.45
AGGREGATE_WINDOW_SECONDS = 5.0

# Merkle batch config
MERKLE_BATCH_WINDOW_SECONDS = 60
MERKLE_FLUSH_POLL_SECONDS = 1.0

CONFIDENCE_THRESHOLD = 0.45
# COCO class ids: person, bicycle, car, motorcycle, bus, truck
ROAD_TARGET_CLASS_IDS = [0, 1, 2, 3, 5, 7]

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Global state
frame_buffer = {"raw": None, "ann": None}
latest_events = []
lock = threading.Lock()

# Load YOLO model
MODEL_CANDIDATES = ["yolo11n.pt", "yolo11m.pt", "yolo11x.pt"]
selected_model = next((m for m in MODEL_CANDIDATES if Path(m).exists()), MODEL_CANDIDATES[0])

if torch.backends.mps.is_available():
    DEVICE = "mps"
    print("[INFO] Apple M-series GPU (MPS) detected, using hardware acceleration.")
else:
    DEVICE = "cpu"
    print("[INFO] MPS not available, using CPU.")

print(f"[INFO] Using YOLO model: {selected_model} on device: {DEVICE}")
model = YOLO(selected_model)
video_source = "https://cctv1.kctmc.nat.gov.tw/6e559e58/"

# Ensure evidence dir exists
EVIDENCE_DIR.mkdir(exist_ok=True)


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                pass


manager = ConnectionManager()


def get_fabric_config():
    return build_fabric_env(FABRIC_SAMPLES_PATH)


def resolve_stream_source(raw_source: str) -> str:
    source = raw_source.strip()
    lower = source.lower()
    media_exts = (".m3u8", ".mp4", ".ts", ".avi", ".mov", ".mkv", ".rtsp")
    if lower.endswith(media_exts):
        return source

    if lower.startswith(("http://", "https://")):
        base = source.rstrip("/")
        candidates = [
            source,
            f"{base}/index.m3u8",
            f"{base}/playlist.m3u8",
            f"{base}/live.m3u8",
        ]
        for candidate in candidates:
            cap = cv2.VideoCapture(candidate)
            ok = cap.isOpened()
            cap.release()
            if ok:
                print(f"[INFO] Web app stream source resolved: {candidate}")
                return candidate
        print(f"[WARN] Stream source unresolved, falling back to original: {source}")
    return source


def _normalize_event_json_payload(raw_bytes: bytes) -> bytes:
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
        if isinstance(data, dict):
            data = dict(data)
            data.pop("_anchor", None)
            data.pop("_merkle", None)
            # Derived fields must be excluded from content hash.
            data.pop("evidence_hash", None)
            data.pop("evidence_hash_list", None)
        return json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
    except Exception:
        return raw_bytes


def compute_hash(json_bytes: bytes, img_bytes: Optional[bytes] = None) -> str:
    sha = hashlib.sha256()
    sha.update(_normalize_event_json_payload(json_bytes))
    if img_bytes:
        sha.update(img_bytes)
    return sha.hexdigest()


def sha256_digest(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def build_merkle_root_and_proofs(leaf_hashes: List[str]) -> Tuple[str, List[List[Dict[str, str]]]]:
    if not leaf_hashes:
        raise ValueError("leaf_hashes cannot be empty")

    levels: List[List[bytes]] = [[bytes.fromhex(h) for h in leaf_hashes]]

    while len(levels[-1]) > 1:
        current = levels[-1]
        nxt: List[bytes] = []
        for i in range(0, len(current), 2):
            left = current[i]
            right = current[i + 1] if i + 1 < len(current) else current[i]
            nxt.append(sha256_digest(left + right))
        levels.append(nxt)

    root = levels[-1][0].hex()

    proofs: List[List[Dict[str, str]]] = []
    for leaf_idx in range(len(leaf_hashes)):
        idx = leaf_idx
        proof: List[Dict[str, str]] = []
        for level in levels[:-1]:
            if idx % 2 == 0:
                sibling_idx = idx + 1 if idx + 1 < len(level) else idx
                position = "right"
            else:
                sibling_idx = idx - 1
                position = "left"
            proof.append({"position": position, "hash": level[sibling_idx].hex()})
            idx //= 2
        proofs.append(proof)

    return root, proofs


def apply_merkle_proof(leaf_hash: str, proof: List[Dict[str, str]]) -> str:
    try:
        node = bytes.fromhex(leaf_hash)
        for step in proof:
            sibling = bytes.fromhex(step["hash"])
            if step.get("position") == "left":
                node = sha256_digest(sibling + node)
            else:
                node = sha256_digest(node + sibling)
        return node.hex()
    except Exception:
        return ""


def get_latest_block_number(env: Dict[str, str], channel: str) -> Optional[int]:
    cmd = ["peer", "channel", "getinfo", "-c", channel]
    proc = subprocess.run(cmd, env=env, text=True, capture_output=True)
    if proc.returncode != 0:
        return None

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


def query_chaincode(function_name: str, args: List[str], timeout: int = 12) -> Dict[str, Any]:
    peer_bin = str(Path.home() / "projects" / "fabric-samples" / "bin" / "peer")
    env, _, _ = get_fabric_config()
    env["FABRIC_CFG_PATH"] = str(Path.home() / "projects" / "fabric-samples" / "config")

    cmd = [
        peer_bin,
        "chaincode",
        "query",
        "-C",
        CHANNEL_NAME,
        "-n",
        CHAINCODE_NAME,
        "-c",
        json.dumps({"function": function_name, "Args": args}),
    ]

    proc = subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "chaincode query failed")

    return json.loads(proc.stdout)


def broadcast_sync(payload: Dict[str, Any]):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(manager.broadcast(json.dumps(payload, ensure_ascii=False)))
    finally:
        loop.close()


def write_event_json(path: Path, payload: Dict[str, Any]):
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def build_event_id() -> str:
    return f"event_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"


def bbox_iou(a: List[float], b: List[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    if inter_area <= 0:
        return 0.0

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter_area
    if union <= 0:
        return 0.0
    return inter_area / union


def resolve_class_name(model_names: Any, class_idx: int) -> str:
    if isinstance(model_names, dict):
        return str(model_names.get(class_idx, class_idx))
    if isinstance(model_names, list) and 0 <= class_idx < len(model_names):
        return str(model_names[class_idx])
    return str(class_idx)


class EventAggregator:
    """Track detections across frames with state transitions:
    pending -> confirmed -> closed.
    Only confirmed tracks are emitted when they are closed (missed for M frames).
    """

    def __init__(
        self,
        min_frames: int = AGGREGATE_MIN_FRAMES,
        max_missed_frames: int = AGGREGATE_MAX_MISSED_FRAMES,
        iou_threshold: float = AGGREGATE_IOU_THRESHOLD,
        window_seconds: float = AGGREGATE_WINDOW_SECONDS,
    ):
        self.min_frames = min_frames
        self.max_missed_frames = max_missed_frames
        self.iou_threshold = iou_threshold
        self.window_seconds = window_seconds
        self.tracks: Dict[str, Dict[str, Any]] = {}
        self.track_seq = 0

    def _new_track(self, det: Dict[str, Any], now: float) -> str:
        self.track_seq += 1
        track_id = f"trk_{self.track_seq}"
        self.tracks[track_id] = {
            "track_id": track_id,
            "state": "pending",
            "class_name": det["class_name"],
            "bbox": det["bbox"],
            "start_ts": now,
            "last_seen": now,
            "count": 1,
            "missed_frames": 0,
            "confidence_sum": det["confidence"],
            "max_confidence": det["confidence"],
            "last_detection": det,
        }
        return track_id

    def _to_frame_detections(self, detections, model_names: Any) -> List[Dict[str, Any]]:
        if detections is None or len(detections) == 0:
            return []

        xyxy = detections.xyxy.tolist()
        cls_values = detections.cls.tolist()
        conf_values = detections.conf.tolist()

        frame_detections = []
        for i, box in enumerate(xyxy):
            class_idx = int(cls_values[i])
            class_name = resolve_class_name(model_names, class_idx)
            frame_detections.append(
                {
                    "class_idx": class_idx,
                    "class_name": class_name,
                    "confidence": float(conf_values[i]),
                    "bbox": [float(v) for v in box],
                }
            )
        return frame_detections

    def _close_track(self, track: Dict[str, Any], closed_at: float) -> Dict[str, Any]:
        duration = max(0.0, closed_at - track["start_ts"])
        frame_count = int(track["count"])
        avg_conf = track["confidence_sum"] / max(frame_count, 1)
        return {
            "event_id": build_event_id(),
            "timestamp": closed_at,
            "start_ts": track["start_ts"],
            "end_ts": closed_at,
            "duration": round(duration, 3),
            "track_id": track["track_id"],
            "top_class": track["class_name"],
            "object_count": 1,
            "avg_confidence": round(avg_conf, 4),
            "max_confidence": round(track["max_confidence"], 4),
            "frame_count": frame_count,
            "state_flow": ["pending", "confirmed", "closed"],
            "detections": [
                {
                    "class": track["class_name"],
                    "confidence": round(track["last_detection"]["confidence"], 4),
                    "bbox": [round(x, 2) for x in track["last_detection"]["bbox"]],
                }
            ],
            "evidence_hash_list": [],
        }

    def update(self, detections, model_names: Any) -> List[Dict[str, Any]]:
        now = time.time()
        frame_detections = self._to_frame_detections(detections, model_names)
        matched_track_ids = set()

        for det in frame_detections:
            best_track_id = None
            best_iou = self.iou_threshold

            for track_id, track in self.tracks.items():
                if track_id in matched_track_ids:
                    continue
                if track["state"] == "closed":
                    continue
                if track["class_name"] != det["class_name"]:
                    continue
                if now - track["last_seen"] > self.window_seconds:
                    continue

                iou = bbox_iou(track["bbox"], det["bbox"])
                if iou >= best_iou:
                    best_iou = iou
                    best_track_id = track_id

            if best_track_id is None:
                new_track_id = self._new_track(det, now)
                matched_track_ids.add(new_track_id)
                continue

            track = self.tracks[best_track_id]
            track["bbox"] = det["bbox"]
            track["last_seen"] = now
            track["count"] += 1
            track["missed_frames"] = 0
            track["confidence_sum"] += det["confidence"]
            track["max_confidence"] = max(track["max_confidence"], det["confidence"])
            track["last_detection"] = det
            if track["state"] == "pending" and track["count"] >= self.min_frames:
                track["state"] = "confirmed"
            matched_track_ids.add(best_track_id)

        for track_id, track in self.tracks.items():
            if track_id not in matched_track_ids and track["state"] != "closed":
                track["missed_frames"] += 1

        events: List[Dict[str, Any]] = []
        close_ids = []

        for track_id, track in self.tracks.items():
            if track["state"] == "closed":
                close_ids.append(track_id)
                continue

            if now - track["last_seen"] > self.window_seconds:
                track["missed_frames"] = max(track["missed_frames"], self.max_missed_frames + 1)

            if track["state"] == "pending" and track["count"] >= self.min_frames:
                track["state"] = "confirmed"

            if track["missed_frames"] > self.max_missed_frames:
                if track["state"] == "confirmed":
                    track["state"] = "closed"
                    events.append(self._close_track(track, now))
                close_ids.append(track_id)

        for track_id in close_ids:
            self.tracks.pop(track_id, None)

        return events


class MerkleBatchManager:
    def __init__(self, window_seconds: int = MERKLE_BATCH_WINDOW_SECONDS):
        self.window_seconds = window_seconds
        self.lock = threading.Lock()
        self.pending_events: List[Dict[str, Any]] = []
        self.window_started_at: Optional[float] = None
        self.flush_thread = threading.Thread(target=self._flush_worker, daemon=True)
        self.flush_thread.start()

    def add_event(self, event_entry: Dict[str, Any]):
        should_flush = False
        with self.lock:
            if self.window_started_at is None:
                self.window_started_at = event_entry.get("timestamp", time.time())
            self.pending_events.append(event_entry)
            if time.time() - self.window_started_at >= self.window_seconds:
                should_flush = True

        if should_flush:
            self.flush(force=True)

    def _flush_worker(self):
        while True:
            time.sleep(MERKLE_FLUSH_POLL_SECONDS)
            self.flush(force=False)

    def flush(self, force: bool = False):
        batch_events: List[Dict[str, Any]] = []
        window_start = None
        window_end = None

        with self.lock:
            if not self.pending_events:
                return

            if not force and self.window_started_at is not None:
                if time.time() - self.window_started_at < self.window_seconds:
                    return

            batch_events = self.pending_events
            window_start = self.window_started_at or time.time()
            window_end = time.time()
            self.pending_events = []
            self.window_started_at = None

        if batch_events:
            self._anchor_batch(batch_events, float(window_start), float(window_end))

    def _anchor_batch(self, batch_events: List[Dict[str, Any]], window_start: float, window_end: float):
        leaf_hashes = [e["evidence_hash"] for e in batch_events]
        merkle_root, proofs = build_merkle_root_and_proofs(leaf_hashes)
        batch_id = f"batch_{int(window_start)}_{int(window_end)}_{uuid.uuid4().hex[:6]}"

        manifest_path = EVIDENCE_DIR / f"{batch_id}.json"
        manifest = {
            "batch_id": batch_id,
            "window_start": int(window_start),
            "window_end": int(window_end),
            "event_count": len(batch_events),
            "merkle_root": merkle_root,
            "events": [
                {
                    "event_id": e["event_id"],
                    "evidence_hash": e["evidence_hash"],
                    "leaf_index": i,
                    "proof": proofs[i],
                }
                for i, e in enumerate(batch_events)
            ],
        }

        tx_id = ""
        block_number = None
        status = "Anchored"
        error_msg = ""

        try:
            env, orderer_ca, org2_tls = get_fabric_config()
            event_ids = [e["event_id"] for e in batch_events]
            args = [
                batch_id,
                CAMERA_ID,
                "merkle_batch",
                str(len(batch_events)),
                merkle_root,
                f"file://{manifest_path.name}",
                json.dumps(event_ids, ensure_ascii=False),
            ]
            invoke_res = invoke_chaincode(
                env,
                orderer_ca,
                org2_tls,
                CHANNEL_NAME,
                CHAINCODE_NAME,
                "CreateEvidenceBatch",
                args,
            )
            tx_id = invoke_res.get("tx_id", "")
            block_number = get_latest_block_number(env, CHANNEL_NAME)
            print(
                f"[MERKLE] Anchored batch {batch_id}, events={len(batch_events)}, "
                f"root={merkle_root[:12]}..., tx={tx_id or 'N/A'}"
            )
        except Exception as e:
            status = "Failed"
            error_msg = str(e)
            print(f"[ERROR] Merkle batch anchor failed for {batch_id}: {e}")

        manifest["status"] = status
        manifest["tx_id"] = tx_id
        manifest["block_number"] = block_number
        if error_msg:
            manifest["error"] = error_msg
        write_event_json(manifest_path, manifest)

        for i, entry in enumerate(batch_events):
            event_json_path = entry["json_path"]
            event_data = {}
            try:
                with event_json_path.open("r", encoding="utf-8") as f:
                    event_data = json.load(f)
            except Exception:
                event_data = {
                    "event_id": entry["event_id"],
                    "top_class": entry.get("top_class", "unknown"),
                    "object_count": entry.get("object_count", 0),
                }

            event_data["evidence_hash_list"] = [entry["evidence_hash"]]
            event_data["_merkle"] = {
                "batchId": batch_id,
                "windowStart": int(window_start),
                "windowEnd": int(window_end),
                "leafIndex": i,
                "proof": proofs[i],
                "proofLength": len(proofs[i]),
                "merkleRoot": merkle_root,
                "batchSize": len(batch_events),
            }
            event_data["_anchor"] = {
                "txId": tx_id,
                "blockNumber": block_number,
                "anchoredAt": int(time.time()),
                "status": status,
            }

            write_event_json(event_json_path, event_data)

            event_info = {
                "id": entry["event_id"],
                "time": time.strftime("%H:%M:%S", time.localtime(entry["timestamp"])),
                "type": entry.get("top_class", "unknown"),
                "count": entry.get("object_count", 0),
                "hash": entry["evidence_hash"],
                "status": status,
                "tx_id": tx_id,
                "block_number": block_number,
                "batch_id": batch_id,
                "batch_size": len(batch_events),
                "merkle_root": merkle_root,
            }
            broadcast_sync(event_info)


batch_manager = MerkleBatchManager(MERKLE_BATCH_WINDOW_SECONDS)


def process_event_worker(event_data: Dict[str, Any], frame_bytes: Optional[bytes]):
    if frame_bytes is None:
        return

    event_id = str(event_data.get("event_id") or build_event_id())
    event_data = dict(event_data)
    event_data["event_id"] = event_id

    json_path = EVIDENCE_DIR / f"{event_id}.json"
    img_path = EVIDENCE_DIR / f"{event_id}.jpg"

    # Persist evidence first (event payload + raw frame)
    write_event_json(json_path, event_data)
    with img_path.open("wb") as f:
        f.write(frame_bytes)

    with json_path.open("rb") as f:
        json_bytes = f.read()
    evidence_hash = compute_hash(json_bytes, frame_bytes)

    event_data["evidence_hash"] = evidence_hash
    event_data["evidence_hash_list"] = [evidence_hash]
    write_event_json(json_path, event_data)

    batch_manager.add_event(
        {
            "event_id": event_id,
            "timestamp": float(event_data.get("timestamp", time.time())),
            "top_class": event_data.get("top_class", "unknown"),
            "object_count": int(event_data.get("object_count", 0)),
            "evidence_hash": evidence_hash,
            "json_path": json_path,
            "img_path": img_path,
        }
    )


def detection_loop():
    global frame_buffer

    source = resolve_stream_source(video_source)
    cap = cv2.VideoCapture(source)
    fail_count = 0
    aggregator = EventAggregator()

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
            conf=CONFIDENCE_THRESHOLD,
            classes=ROAD_TARGET_CLASS_IDS,
            imgsz=640,
            device=DEVICE,
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

        # Aggregation with pending -> confirmed -> closed state transitions.
        closed_events = aggregator.update(results.boxes, model.names)
        for event_data in closed_events:
            if raw_snapshot is None:
                continue
            print(
                f"[AGG] Closed event {event_data['event_id']} class={event_data['top_class']} "
                f"frames={event_data['frame_count']} duration={event_data['duration']}s"
            )
            t = threading.Thread(target=process_event_worker, args=(event_data, raw_snapshot), daemon=True)
            t.start()


# Start detection thread
t = threading.Thread(target=detection_loop, daemon=True)
t.start()


@app.get("/")
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


def gen_frames(capture_type="raw"):
    while True:
        with lock:
            if frame_buffer[capture_type] is None:
                time.sleep(0.1)
                continue
            frame = frame_buffer[capture_type]
        yield (b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
        time.sleep(0.05)


@app.get("/video_feed/{stream_type}")
def video_feed(stream_type: str):
    if stream_type not in ["raw", "ann"]:
        stream_type = "raw"
    return StreamingResponse(gen_frames(stream_type), media_type="multipart/x-mixed-replace; boundary=frame")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.post("/api/verify/{event_id}")
async def verify_evidence(event_id: str):
    try:
        json_path = EVIDENCE_DIR / f"{event_id}.json"
        img_path = EVIDENCE_DIR / f"{event_id}.jpg"

        if not json_path.exists() or not img_path.exists():
            return JSONResponse({"status": "error", "message": "Local evidence not found"}, status_code=404)

        with json_path.open("rb") as f:
            json_bytes = f.read()
        with img_path.open("rb") as f:
            img_bytes = f.read()

        local_hash = compute_hash(json_bytes, img_bytes)
        local_data = json.loads(json_bytes.decode("utf-8"))

        merkle_meta = local_data.get("_merkle", {}) if isinstance(local_data, dict) else {}
        anchor_meta = local_data.get("_anchor", {}) if isinstance(local_data, dict) else {}
        stored_leaf_hash = local_data.get("evidence_hash", "") if isinstance(local_data, dict) else ""
        leaf_hash = stored_leaf_hash or local_hash

        # Event keys are also written on chain by CreateEvidenceBatch.
        onchain_data = query_chaincode("ReadEvidence", [event_id])
        chain_hash = onchain_data.get("evidenceHash", "")

        if merkle_meta:
            proof = merkle_meta.get("proof", [])
            proof_root = apply_merkle_proof(leaf_hash, proof)
            expected_root = merkle_meta.get("merkleRoot", "")
            proof_valid = proof_root == expected_root == chain_hash
            return {
                "status": "success",
                "mode": "merkle_batch",
                "match": proof_valid,
                "local_hash": local_hash,
                "leaf_hash": leaf_hash,
                "local_matches_leaf": bool(local_hash == leaf_hash),
                "proof_root": proof_root,
                "chain_hash": chain_hash,
                "batch_id": merkle_meta.get("batchId"),
                "batch_size": merkle_meta.get("batchSize"),
                "proof_length": len(proof),
                "onchain_time": onchain_data.get("timestamp"),
                "tx_id": anchor_meta.get("txId", ""),
                "block_number": anchor_meta.get("blockNumber"),
                "history_key": event_id,
            }

        match = local_hash == chain_hash
        return {
            "status": "success",
            "mode": "direct",
            "match": match,
            "local_hash": local_hash,
            "chain_hash": chain_hash,
            "onchain_time": onchain_data.get("timestamp"),
            "tx_id": anchor_meta.get("txId", ""),
            "block_number": anchor_meta.get("blockNumber"),
            "history_key": event_id,
        }
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/api/history/{event_id}")
async def get_history_for_key(event_id: str):
    try:
        history = query_chaincode("GetHistoryForKey", [event_id], timeout=20)
        normalized = []
        for item in history:
            value = item.get("value")
            if isinstance(value, str) and value.strip():
                try:
                    value = json.loads(value)
                except Exception:
                    pass
            normalized.append(
                {
                    "txId": item.get("txId", ""),
                    "timestamp": item.get("timestamp"),
                    "isDelete": bool(item.get("isDelete", False)),
                    "value": value,
                }
            )
        return {"status": "success", "history": normalized}
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
