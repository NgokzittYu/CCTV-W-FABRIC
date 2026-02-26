import cv2
import time
import json
import asyncio
import base64
import hashlib
import threading
import subprocess
from pathlib import Path
from collections import Counter
from typing import List

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from ultralytics import YOLO

# Reuse logic from anchor_to_fabric.py
from anchor_to_fabric import build_fabric_env, invoke_create_evidence, run

# Configuration
FABRIC_SAMPLES_PATH = Path("../fabric-samples").resolve()
EVIDENCE_DIR = Path("evidences").resolve()
CAMERA_ID = "cctv-kctmc-apple-01"
CHAINCODE_NAME = "evidence"
CHANNEL_NAME = "mychannel"
ANCHOR_INTERVAL = 10.0  # Seconds between anchors for same event
CONFIDENCE_THRESHOLD = 0.45
# COCO class ids: person, bicycle, car, motorcycle, bus, truck
ROAD_TARGET_CLASS_IDS = [0, 1, 2, 3, 5, 7]

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Global State
frame_buffer = {"raw": None, "ann": None}
last_anchor_time = 0
latest_events = []  # List of dicts for UI
lock = threading.Lock()

# Load YOLO (prefer 11x; fallback to 11m if unavailable)
MODEL_CANDIDATES = ["yolo11x.pt", "yolo11m.pt", "yolo11n.pt"]
selected_model = next((m for m in MODEL_CANDIDATES if Path(m).exists()), MODEL_CANDIDATES[0])
if selected_model != "yolo11x.pt":
    print(f"[WARN] yolo11x.pt not found, fallback to {selected_model}")
model = YOLO(selected_model)
video_source = "https://cctv1.kctmc.nat.gov.tw/6e559e58/" # Default source, can be overridden

# Ensure evidence dir exists
EVIDENCE_DIR.mkdir(exist_ok=True)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
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
                print(f"[INFO] WebApp using stream source: {candidate}")
                return candidate
        print(f"[WARN] WebApp stream source unresolved, fallback to original: {source}")
    return source

def compute_hash(json_bytes, img_bytes=None):
    sha = hashlib.sha256()
    # Exclude local anchor receipt metadata so local verification matches on-chain hash.
    try:
        data = json.loads(json_bytes.decode("utf-8"))
        if isinstance(data, dict) and "_anchor" in data:
            data = dict(data)
            data.pop("_anchor", None)
        normalized = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        sha.update(normalized)
    except Exception:
        sha.update(json_bytes)
    if img_bytes:
        sha.update(img_bytes)
    return sha.hexdigest()

def anchor_worker(event_data, frame_bytes):
    """Background task to anchor evidence to Fabric"""
    global latest_events
    
    timestamp = int(time.time())
    event_id = f"event_{timestamp}"
    
    # 1. Save to Disk
    json_path = EVIDENCE_DIR / f"{event_id}.json"
    img_path = EVIDENCE_DIR / f"{event_id}.jpg"
    
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(event_data, f, indent=2)
    
    with open(img_path, "wb") as f:
        f.write(frame_bytes)
        
    # 2. Compute Hash
    with open(json_path, "rb") as f:
        json_bytes = f.read()
        
    evidence_hash = compute_hash(json_bytes, frame_bytes)
    
    # 3. Anchor to Fabric
    # CreateEvidence(id, cameraId, eventType, objectCount, evidenceHash, rawDataUrl)
    # Re-using logic from anchor_to_fabric but we need to pass env
    env, orderer_ca, org2_tls = get_fabric_config()
    
    top_class = event_data.get("top_class", "unknown")
    obj_count = event_data.get("object_count", 0)
    
    args = [
        event_id,
        CAMERA_ID,
        f"detection_{top_class}",
        str(obj_count),
        evidence_hash,
        f"file://{event_id}.json"
    ]
    
    try:
        # This blocks, so we run in thread. In production use Celery/Task Queue.
        invoke_res = invoke_create_evidence(env, orderer_ca, org2_tls, CHANNEL_NAME, CHAINCODE_NAME, args)
        tx_id = invoke_res.get("tx_id", "")

        block_number = None
        info_proc = subprocess.run(
            ["/home/wazteh/projects/fabric-samples/bin/peer", "channel", "getinfo", "-c", CHANNEL_NAME],
            env=env,
            text=True,
            capture_output=True,
            timeout=10,
        )
        if info_proc.returncode == 0 and "Blockchain info:" in (info_proc.stdout or ""):
            payload = info_proc.stdout.split("Blockchain info:", 1)[1].strip()
            try:
                chain_info = json.loads(payload)
                height = int(chain_info.get("height", 0))
                if height > 0:
                    block_number = height - 1
            except Exception:
                block_number = None

        # Persist local anchor receipt for later verification UI
        event_data["_anchor"] = {
            "txId": tx_id,
            "blockNumber": block_number,
            "anchoredAt": timestamp,
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(event_data, f, indent=2, ensure_ascii=False)

        status = "Anchored"
        print(f"[SUCCESS] Anchored {event_id}")
    except Exception as e:
        status = "Failed"
        print(f"[ERROR] Anchor failed: {e}")

    # 4. Notify UI
    event_info = {
        "id": event_id,
        "time": time.strftime("%H:%M:%S", time.localtime(timestamp)),
        "type": top_class,
        "count": obj_count,
        "hash": evidence_hash,
        "status": status,
        "tx_id": tx_id,
        "block_number": block_number
    }
    
    # Broadcast to Websockets
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(manager.broadcast(json.dumps(event_info)))
    loop.close()


def detection_loop():
    global last_anchor_time, frame_buffer

    source = resolve_stream_source(video_source)
    cap = cv2.VideoCapture(source)
    fail_count = 0
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
            
        # Inference
        results = model.predict(
            frame,
            conf=CONFIDENCE_THRESHOLD,
            classes=ROAD_TARGET_CLASS_IDS,
            verbose=False,
        )[0]
        annotated_frame = results.plot()
        
        # Update Buffers
        with lock:
            ret, buffer_raw = cv2.imencode('.jpg', frame)
            ret, buffer_ann = cv2.imencode('.jpg', annotated_frame)
            frame_buffer["raw"] = buffer_raw.tobytes()
            frame_buffer["ann"] = buffer_ann.tobytes()

        # Check for Anchoring
        # Logic: If objects detected AND (now - last_anchor > 10s)
        detections = results.boxes
        if len(detections) > 0:
            current_time = time.time()
            if current_time - last_anchor_time > ANCHOR_INTERVAL:
                # Trigger Anchor
                classes = [model.names[int(c)] for c in detections.cls]
                top_class = Counter(classes).most_common(1)[0][0]
                
                event_data = {
                    "event_id": f"event_{int(current_time)}",
                    "timestamp": current_time,
                    "detections": [
                        {"class": model.names[int(c)], "confidence": float(conf)}
                        for c, conf in zip(detections.cls, detections.conf)
                    ],
                    "top_class": top_class,
                    "object_count": len(detections)
                }
                
                # Start background thread for blockchain ops
                t = threading.Thread(target=anchor_worker, args=(event_data, frame_buffer["raw"]))
                t.start()
                
                last_anchor_time = current_time
        
        # Free up CPU slightly
        time.sleep(0.01)

# Start Detection Thread
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
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

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
        # Simulate verification or run actual verify script
        # For speed, we just check local hash vs chain hash here
        json_path = EVIDENCE_DIR / f"{event_id}.json"
        img_path = EVIDENCE_DIR / f"{event_id}.jpg"

        if not json_path.exists() or not img_path.exists():
            return JSONResponse({"status": "error", "message": "Local evidence not found"}, status_code=404)

        # 1. Local Hash
        with open(json_path, "rb") as f:
            json_bytes = f.read()
        with open(img_path, "rb") as f:
            img_bytes = f.read()
        local_hash = compute_hash(json_bytes, img_bytes)
        local_data = json.loads(json_bytes.decode("utf-8"))
        anchor_meta = local_data.get("_anchor", {})

        # 2. Chain Hash
        peer_bin = "/home/wazteh/projects/fabric-samples/bin/peer"
        env, _, _ = get_fabric_config()
        env["FABRIC_CFG_PATH"] = "/home/wazteh/projects/fabric-samples/config"

        cmd = [
            peer_bin,
            "chaincode",
            "query",
            "-C",
            CHANNEL_NAME,
            "-n",
            CHAINCODE_NAME,
            "-c",
            json.dumps({"function": "ReadEvidence", "Args": [event_id]}),
        ]

        proc = subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=12)
        if proc.returncode != 0:
            return JSONResponse(
                {"status": "error", "message": f"Chain error: {proc.stderr.strip()}"},
                status_code=500,
            )

        onchain_data = json.loads(proc.stdout)
        chain_hash = onchain_data.get("evidenceHash", "")
        match = (local_hash == chain_hash)

        return {
            "status": "success",
            "match": match,
            "local_hash": local_hash,
            "chain_hash": chain_hash,
            "timestamp": onchain_data.get("timestamp"),
            "onchain_time": onchain_data.get("timestamp"),
            "tx_id": anchor_meta.get("txId", ""),
            "block_number": anchor_meta.get("blockNumber"),
        }
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
