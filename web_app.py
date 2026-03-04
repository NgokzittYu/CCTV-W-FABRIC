import asyncio
from datetime import datetime
import base64
import hashlib
import json
import subprocess
import tempfile
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
from config import SETTINGS

# Configuration
FABRIC_SAMPLES_PATH = SETTINGS.fabric_samples_path
EVIDENCE_DIR = SETTINGS.evidence_dir
CAMERA_ID = SETTINGS.camera_id
CHAINCODE_NAME = SETTINGS.chaincode_name
CHANNEL_NAME = SETTINGS.channel_name
DEVICE_CERT_PATH = SETTINGS.device_cert_path
DEVICE_KEY_PATH = SETTINGS.device_key_path
DEVICE_SIGN_ALGO = SETTINGS.device_sign_algo
DEVICE_SIGNATURE_REQUIRED = SETTINGS.device_signature_required

# Event aggregation config
AGGREGATE_MIN_FRAMES = SETTINGS.aggregate_min_frames
AGGREGATE_MAX_MISSED_FRAMES = SETTINGS.aggregate_max_missed_frames
AGGREGATE_IOU_THRESHOLD = SETTINGS.aggregate_iou_threshold
AGGREGATE_WINDOW_SECONDS = SETTINGS.aggregate_window_seconds

# Merkle batch config
MERKLE_BATCH_WINDOW_SECONDS = SETTINGS.merkle_batch_window_seconds
MERKLE_FLUSH_POLL_SECONDS = SETTINGS.merkle_flush_poll_seconds

# Auto workorder trigger config
AUTO_CREATE_WORKORDER = True  # Enable/disable auto workorder creation
WORKORDER_TRIGGER_RULES = [
    {
        "violation_level": "high",
        "auto_assign_org": "Org1MSP",
        "default_deadline_days": 7
    },
    {
        "violation_level": "critical",
        "auto_assign_org": "Org1MSP",
        "default_deadline_days": 3
    }
]

CONFIDENCE_THRESHOLD = SETTINGS.confidence_threshold
# COCO class ids: person, bicycle, car, motorcycle, bus, truck
ROAD_TARGET_CLASS_IDS = SETTINGS.road_target_class_ids

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Global state
frame_buffer = {"raw": None, "ann": None}
latest_events = []
lock = threading.Lock()

# Load YOLO model
MODEL_CANDIDATES = SETTINGS.model_candidates
selected_model = next((m for m in MODEL_CANDIDATES if Path(m).exists()), MODEL_CANDIDATES[0])

if torch.backends.mps.is_available():
    DEVICE = "mps"
    print("[INFO] Apple M-series GPU (MPS) detected, using hardware acceleration.")
else:
    DEVICE = "cpu"
    print("[INFO] MPS not available, using CPU.")

print(f"[INFO] Using YOLO model: {selected_model} on device: {DEVICE}")
model = YOLO(selected_model)
video_source = SETTINGS.video_source

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


def build_batch_signature_payload(
    batch_id: str,
    camera_id: str,
    merkle_root: str,
    window_start: int,
    window_end: int,
    event_ids: List[str],
    event_hashes: List[str],
) -> bytes:
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


def _auto_generate_device_material(camera_id: str) -> Tuple[Path, Path]:
    base_dir = Path(tempfile.gettempdir()) / "cctv_device_autogen"
    base_dir.mkdir(parents=True, exist_ok=True)
    key_path = base_dir / f"{camera_id}.key.pem"
    cert_path = base_dir / f"{camera_id}.cert.pem"
    if key_path.exists() and cert_path.exists():
        return cert_path, key_path

    subj = f"/CN=device-{camera_id}@org1.example.com/O=Org1"
    cmd = [
        "openssl",
        "req",
        "-x509",
        "-newkey",
        "ec",
        "-pkeyopt",
        "ec_paramgen_curve:P-256",
        "-nodes",
        "-keyout",
        str(key_path),
        "-out",
        str(cert_path),
        "-days",
        "365",
        "-subj",
        subj,
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "failed to auto-generate device key/cert")
    return cert_path, key_path


def sign_payload_with_device_key(payload_bytes: bytes, key_path: Path) -> str:
    if DEVICE_SIGN_ALGO != "ECDSA_SHA256":
        raise RuntimeError(f"unsupported DEVICE_SIGN_ALGO: {DEVICE_SIGN_ALGO}")
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


def build_batch_signature_material(
    batch_id: str,
    camera_id: str,
    merkle_root: str,
    window_start: int,
    window_end: int,
    event_ids: List[str],
    event_hashes: List[str],
) -> Tuple[str, str, str]:
    payload_bytes = build_batch_signature_payload(
        batch_id,
        camera_id,
        merkle_root,
        int(window_start),
        int(window_end),
        event_ids,
        event_hashes,
    )
    payload_hash = hashlib.sha256(payload_bytes).hexdigest()

    cert_path = DEVICE_CERT_PATH
    key_path = DEVICE_KEY_PATH
    if not cert_path.exists() or not key_path.exists():
        if DEVICE_SIGNATURE_REQUIRED:
            raise RuntimeError(
                f"device cert/key not found: cert={cert_path}, key={key_path}, "
                "set DEVICE_CERT_PATH and DEVICE_KEY_PATH"
            )
        cert_path, key_path = _auto_generate_device_material(camera_id)

    cert_pem = cert_path.read_text(encoding="utf-8").strip()
    signature_b64 = sign_payload_with_device_key(payload_bytes, key_path)
    return cert_pem, signature_b64, payload_hash


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


def query_chaincode(function_name: str, args: List[str], timeout: int = 12) -> Any:
    peer_bin = str(FABRIC_SAMPLES_PATH / "bin" / "peer")
    env, _, _ = get_fabric_config()
    env["FABRIC_CFG_PATH"] = str(FABRIC_SAMPLES_PATH / "config")

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


def _date_str_from_ts(ts_sec: float) -> str:
    return datetime.fromtimestamp(ts_sec).strftime("%Y-%m-%d")


def _resolve_event_paths(event_id: str) -> Tuple[Path, Path]:
    """Resolve json/img paths for an event.
    New layout:  evidences/events/<YYYY-MM-DD>/event_xxx.json
    Fallback:    evidences/event_xxx.json  (legacy flat layout)
    """
    # Try to extract timestamp from event_id  (event_<ms>_<hex>)
    try:
        ts_ms = int(event_id.split("_")[1])
        date_str = _date_str_from_ts(ts_ms / 1000.0)
    except (IndexError, ValueError):
        date_str = None

    # New layout
    if date_str:
        new_dir = EVIDENCE_DIR / "events" / date_str
        json_path = new_dir / f"{event_id}.json"
        img_path = new_dir / f"{event_id}.jpg"
        if json_path.exists():
            return json_path, img_path

    # Fallback to legacy flat layout
    json_path = EVIDENCE_DIR / f"{event_id}.json"
    img_path = EVIDENCE_DIR / f"{event_id}.jpg"
    return json_path, img_path


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

        date_str = _date_str_from_ts(window_start)
        batch_dir = EVIDENCE_DIR / "batches" / date_str
        batch_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = batch_dir / f"{batch_id}.json"
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
            event_hashes = [e["evidence_hash"] for e in batch_events]
            device_cert_pem, signature_b64, payload_hash_hex = build_batch_signature_material(
                batch_id,
                CAMERA_ID,
                merkle_root,
                int(window_start),
                int(window_end),
                event_ids,
                event_hashes,
            )
            args = [
                batch_id,
                CAMERA_ID,
                merkle_root,
                str(int(window_start)),
                str(int(window_end)),
                json.dumps(event_ids, ensure_ascii=False),
                json.dumps(event_hashes, ensure_ascii=False),
                device_cert_pem,
                signature_b64,
                payload_hash_hex,
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
            manifest["payload_hash"] = payload_hash_hex
            manifest["signature_alg"] = DEVICE_SIGN_ALGO

            # Auto-trigger workorder if enabled
            if len(batch_events) >= 5:  # Trigger if 5+ events in batch
                threading.Thread(
                    target=auto_trigger_workorder,
                    args=(batch_id, len(batch_events), "high"),
                    daemon=True
                ).start()
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


def auto_trigger_workorder(batch_id: str, event_count: int, violation_level: str = "high"):
    """Automatically create workorder for violation events"""
    if not AUTO_CREATE_WORKORDER:
        return

    # Find matching rule
    rule = None
    for r in WORKORDER_TRIGGER_RULES:
        if r["violation_level"] == violation_level:
            rule = r
            break

    if not rule:
        print(f"[AUTO-WORKORDER] No rule found for violation level: {violation_level}")
        return

    try:
        order_id = f"order_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        deadline = int(time.time()) + (rule["default_deadline_days"] * 24 * 3600)
        description = f"自动创建：检测到 {event_count} 个违规事件，批次 {batch_id}，需要整改"

        # Use Org2 identity to create workorder (only Org2 has permission)
        env, orderer_ca, org2_tls = get_fabric_config()

        # Save Org1 TLS cert path before overriding
        org1_tls_cert = env["CORE_PEER_TLS_ROOTCERT_FILE"]

        # Override to use Org2 MSP identity
        org2_path = FABRIC_SAMPLES_PATH / "test-network" / "organizations" / "peerOrganizations" / "org2.example.com"
        env["CORE_PEER_LOCALMSPID"] = "Org2MSP"
        env["CORE_PEER_ADDRESS"] = "localhost:9051"
        env["CORE_PEER_TLS_ROOTCERT_FILE"] = org1_tls_cert  # Keep Org1 cert for peer connection
        env["CORE_PEER_MSPCONFIGPATH"] = str(org2_path / "users" / "Admin@org2.example.com" / "msp")

        args = [
            order_id,
            batch_id,
            rule["auto_assign_org"],
            str(deadline),
            description
        ]

        invoke_chaincode(
            env,
            orderer_ca,
            org2_tls,
            CHANNEL_NAME,
            CHAINCODE_NAME,
            "CreateRectificationOrder",
            args,
        )

        print(f"[AUTO-WORKORDER] Created workorder {order_id} for batch {batch_id}")
    except Exception as e:
        print(f"[AUTO-WORKORDER] Failed to create workorder: {e}")


def process_event_worker(event_data: Dict[str, Any], frame_bytes: Optional[bytes]):
    if frame_bytes is None:
        return

    event_id = str(event_data.get("event_id") or build_event_id())
    event_data = dict(event_data)
    event_data["event_id"] = event_id

    ts = float(event_data.get("timestamp", time.time()))
    date_str = _date_str_from_ts(ts)
    event_dir = EVIDENCE_DIR / "events" / date_str
    event_dir.mkdir(parents=True, exist_ok=True)
    json_path = event_dir / f"{event_id}.json"
    img_path = event_dir / f"{event_id}.jpg"

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


@app.get("/workorder")
def workorder_page(request: Request):
    return templates.TemplateResponse("workorder.html", {"request": request})


@app.get("/audit")
def audit_page(request: Request):
    return templates.TemplateResponse("audit.html", {"request": request})


@app.get("/config")
def config_page(request: Request):
    return templates.TemplateResponse("config.html", {"request": request})


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
        json_path, img_path = _resolve_event_paths(event_id)

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

        onchain_data = query_chaincode("ReadEvidence", [event_id])
        if not isinstance(onchain_data, dict):
            raise RuntimeError("unexpected chaincode response for ReadEvidence")
        chain_hash = onchain_data.get("evidenceHash", "")

        if merkle_meta:
            proof = merkle_meta.get("proof", [])
            proof_json = json.dumps(proof, ensure_ascii=False)
            batch_id = str(merkle_meta.get("batchId", "")).strip()
            expected_root = str(merkle_meta.get("merkleRoot", "")).strip().lower()
            proof_root = apply_merkle_proof(leaf_hash, proof)
            verify_event_ok = False
            verify_error = ""
            if batch_id and leaf_hash and expected_root:
                try:
                    verify_raw = query_chaincode(
                        "VerifyEvent",
                        [batch_id, leaf_hash, proof_json, expected_root],
                    )
                    verify_event_ok = bool(verify_raw)
                except Exception as verify_exc:
                    verify_error = str(verify_exc)
            else:
                verify_error = "missing merkle metadata fields"

            local_matches_leaf = bool(local_hash == leaf_hash)
            chain_leaf_match = bool(chain_hash == leaf_hash)
            proof_valid = bool(verify_event_ok and chain_leaf_match and local_matches_leaf)
            result = {
                "status": "success",
                "mode": "merkle_batch",
                "match": proof_valid,
                "local_hash": local_hash,
                "leaf_hash": leaf_hash,
                "local_matches_leaf": local_matches_leaf,
                "chain_leaf_match": chain_leaf_match,
                "verify_event_ok": verify_event_ok,
                "proof_root": proof_root,
                "chain_hash": chain_hash,
                "batch_id": batch_id,
                "batch_size": merkle_meta.get("batchSize"),
                "proof_length": len(proof),
                "onchain_time": onchain_data.get("timestamp"),
                "tx_id": anchor_meta.get("txId", ""),
                "block_number": anchor_meta.get("blockNumber"),
                "history_key": event_id,
            }
            if verify_error:
                result["verify_error"] = verify_error
            return result

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
        error_msg = str(e)
        if "does not exist" in error_msg.lower():
            return JSONResponse({"status": "error", "message": "Event not found on-chain"}, status_code=404)
        return JSONResponse({"status": "error", "message": error_msg}, status_code=500)


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


# ==================== Workorder Management APIs ====================

@app.post("/api/workorder/create")
async def create_workorder(request: Request):
    """Create a new rectification workorder (Org2 only)"""
    try:
        body = await request.json()
        violation_id = body.get("violationId", "").strip()
        description = body.get("description", "").strip()
        assigned_org = body.get("assignedOrg", "").strip()
        deadline = body.get("deadline", 0)

        if not violation_id or not assigned_org:
            return JSONResponse(
                {"status": "error", "message": "violationId and assignedOrg are required"},
                status_code=400
            )

        order_id = f"order_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"

        # Use Org2 identity to create workorder (only Org2 has permission)
        env, orderer_ca, org2_tls = get_fabric_config()

        # Save Org1 TLS cert path before overriding
        org1_tls_cert = env["CORE_PEER_TLS_ROOTCERT_FILE"]

        # Override to use Org2 MSP identity
        org2_path = FABRIC_SAMPLES_PATH / "test-network" / "organizations" / "peerOrganizations" / "org2.example.com"
        env["CORE_PEER_LOCALMSPID"] = "Org2MSP"
        env["CORE_PEER_ADDRESS"] = "localhost:9051"
        env["CORE_PEER_TLS_ROOTCERT_FILE"] = org1_tls_cert  # Keep Org1 cert for peer connection
        env["CORE_PEER_MSPCONFIGPATH"] = str(org2_path / "users" / "Admin@org2.example.com" / "msp")

        args = [order_id, violation_id, assigned_org, str(deadline), description]

        invoke_res = invoke_chaincode(
            env,
            orderer_ca,
            org2_tls,
            CHANNEL_NAME,
            CHAINCODE_NAME,
            "CreateRectificationOrder",
            args,
        )

        return {
            "status": "success",
            "orderId": order_id,
            "txId": invoke_res.get("tx_id", ""),
            "message": "Workorder created successfully"
        }
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/api/workorder/{order_id}/rectify")
async def submit_rectification(order_id: str, request: Request):
    """Submit rectification proof (Org1 only)"""
    try:
        body = await request.json()
        rectification_proof = body.get("rectificationProof", "").strip()
        attachments = body.get("attachments", [])

        if not rectification_proof:
            return JSONResponse(
                {"status": "error", "message": "rectificationProof is required"},
                status_code=400
            )

        attachment_url = ",".join(attachments) if attachments else rectification_proof

        env, orderer_ca, org2_tls = get_fabric_config()
        args = [order_id, attachment_url, rectification_proof]

        invoke_res = invoke_chaincode(
            env,
            orderer_ca,
            org2_tls,
            CHANNEL_NAME,
            CHAINCODE_NAME,
            "SubmitRectification",
            args,
        )

        return {
            "status": "success",
            "orderId": order_id,
            "txId": invoke_res.get("tx_id", ""),
            "message": "Rectification submitted successfully"
        }
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.post("/api/workorder/{order_id}/confirm")
async def confirm_workorder(order_id: str, request: Request):
    """Confirm or reject rectification (Org2 only)"""
    try:
        body = await request.json()
        approved = body.get("approved", False)
        comments = body.get("comments", "").strip()

        # Use Org2 identity to confirm workorder (only Org2 has permission)
        env, orderer_ca, org2_tls = get_fabric_config()

        # Save Org1 TLS cert path before overriding
        org1_tls_cert = env["CORE_PEER_TLS_ROOTCERT_FILE"]

        # Override to use Org2 MSP identity
        org2_path = FABRIC_SAMPLES_PATH / "test-network" / "organizations" / "peerOrganizations" / "org2.example.com"
        env["CORE_PEER_LOCALMSPID"] = "Org2MSP"
        env["CORE_PEER_ADDRESS"] = "localhost:9051"
        env["CORE_PEER_TLS_ROOTCERT_FILE"] = org1_tls_cert  # Keep Org1 cert for peer connection
        env["CORE_PEER_MSPCONFIGPATH"] = str(org2_path / "users" / "Admin@org2.example.com" / "msp")

        args = [order_id, str(approved).lower(), comments]

        invoke_res = invoke_chaincode(
            env,
            orderer_ca,
            org2_tls,
            CHANNEL_NAME,
            CHAINCODE_NAME,
            "ConfirmRectification",
            args,
        )

        return {
            "status": "success",
            "orderId": order_id,
            "approved": approved,
            "txId": invoke_res.get("tx_id", ""),
            "message": f"Workorder {'approved' if approved else 'rejected'} successfully"
        }
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/api/workorder/overdue")
async def query_overdue_workorders(org: Optional[str] = None, page: int = 1, limit: int = 20):
    """Query overdue workorders"""
    try:
        # Query all rectification orders from chaincode
        # Note: This requires a new chaincode function QueryOverdueWorkOrders
        # For now, we'll return a placeholder response
        return {
            "status": "success",
            "message": "Overdue workorder query not yet implemented in chaincode",
            "data": [],
            "page": page,
            "limit": limit,
            "total": 0
        }
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/api/workorder/{order_id}")
async def get_workorder_detail(order_id: str):
    """Get workorder details"""
    try:
        order_data = query_chaincode("ReadRectificationOrder", [order_id])

        if not order_data:
            return JSONResponse(
                {"status": "error", "message": "Workorder not found"},
                status_code=404
            )

        # Calculate if overdue
        deadline = order_data.get("deadline", 0)
        current_time = int(time.time())
        is_overdue = deadline > 0 and current_time > deadline and order_data.get("status") == "OPEN"

        return {
            "status": "success",
            "data": {
                **order_data,
                "isOverdue": is_overdue,
                "overdueBy": max(0, current_time - deadline) if is_overdue else 0
            }
        }
    except Exception as e:
        error_msg = str(e)
        if "does not exist" in error_msg.lower():
            return JSONResponse({"status": "error", "message": "Workorder not found"}, status_code=404)
        return JSONResponse({"status": "error", "message": error_msg}, status_code=500)


@app.get("/api/audit/export")
async def export_audit_trail(
    batch_id: Optional[str] = None,
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    format: str = "json"
):
    """Export audit trail for a batch"""
    try:
        if not batch_id:
            return JSONResponse(
                {"status": "error", "message": "batch_id is required"},
                status_code=400
            )

        audit_data = query_chaincode("ExportAuditTrail", [batch_id], timeout=30)

        if not audit_data:
            return JSONResponse(
                {"status": "error", "message": "Audit trail not found"},
                status_code=404
            )

        # Add report metadata
        report = {
            "reportId": f"audit_{int(time.time())}_{uuid.uuid4().hex[:6]}",
            "generatedAt": int(time.time()),
            "generatedBy": "system",
            "batchId": batch_id,
            "auditData": audit_data,
            "signature": hashlib.sha256(json.dumps(audit_data, sort_keys=True).encode()).hexdigest()
        }

        if format == "json":
            return report
        else:
            return JSONResponse(
                {"status": "error", "message": f"Format {format} not yet supported"},
                status_code=400
            )
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


@app.get("/api/config/auto-workorder")
async def get_auto_workorder_config():
    """Get auto workorder configuration"""
    return {
        "status": "success",
        "config": {
            "enabled": AUTO_CREATE_WORKORDER,
            "rules": WORKORDER_TRIGGER_RULES
        }
    }


@app.post("/api/config/auto-workorder")
async def update_auto_workorder_config(request: Request):
    """Update auto workorder configuration"""
    global AUTO_CREATE_WORKORDER, WORKORDER_TRIGGER_RULES

    try:
        body = await request.json()

        if "enabled" in body:
            AUTO_CREATE_WORKORDER = bool(body["enabled"])

        if "rules" in body:
            WORKORDER_TRIGGER_RULES = body["rules"]

        return {
            "status": "success",
            "message": "Configuration updated successfully",
            "config": {
                "enabled": AUTO_CREATE_WORKORDER,
                "rules": WORKORDER_TRIGGER_RULES
            }
        }
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
