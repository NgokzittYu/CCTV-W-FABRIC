import asyncio
import json
import threading
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import torch
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from ultralytics import YOLO

from config import SETTINGS
from services.detection_service import MerkleBatchManager, start_detection_loop
from services.fabric_client import build_fabric_env, get_fabric_config, query_chaincode
from services.merkle_utils import apply_merkle_proof
from services.workorder_service import (
    confirm_rectification,
    create_workorder,
    export_audit_trail,
    query_overdue_workorders,
    query_workorder_by_id,
    submit_rectification,
)

# Configuration
EVIDENCE_DIR = SETTINGS.evidence_dir
CAMERA_ID = SETTINGS.camera_id
CHAINCODE_NAME = SETTINGS.chaincode_name
CHANNEL_NAME = SETTINGS.channel_name
CONFIDENCE_THRESHOLD = SETTINGS.confidence_threshold
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
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


manager = ConnectionManager()


def broadcast_sync(payload: Dict):
    """Synchronous broadcast wrapper."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(manager.broadcast(payload))
        else:
            loop.run_until_complete(manager.broadcast(payload))
    except Exception:
        pass


# Routes
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


@app.get("/video_feed/{stream_type}")
def video_feed(stream_type: str):
    """Stream video frames (raw or annotated)."""
    def generate():
        while True:
            with lock:
                frame_data = frame_buffer.get("ann" if stream_type == "annotated" else "raw")
            if frame_data:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + frame_data + b"\r\n")

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.post("/api/verify/{event_id}")
def verify_evidence(event_id: str):
    """Verify evidence using Merkle proof."""
    json_path = EVIDENCE_DIR / f"{event_id}.json"
    if not json_path.exists():
        return JSONResponse({"error": "Event not found"}, status_code=404)

    event_data = json.loads(json_path.read_text(encoding="utf-8"))
    merkle_info = event_data.get("_merkle")

    if not merkle_info:
        return JSONResponse({"error": "No Merkle proof available"}, status_code=400)

    evidence_hash = event_data.get("evidence_hash", "")
    proof = merkle_info.get("proof", [])
    expected_root = merkle_info.get("merkleRoot", "")

    computed_root = apply_merkle_proof(evidence_hash, proof)
    verified = computed_root == expected_root

    return JSONResponse({
        "verified": verified,
        "evidenceHash": evidence_hash,
        "computedRoot": computed_root,
        "expectedRoot": expected_root,
        "batchId": merkle_info.get("batchId"),
    })


@app.get("/api/history/{event_id}")
def get_event_history(event_id: str):
    """Get event history from blockchain."""
    try:
        fabric_samples = Path(SETTINGS.fabric_samples_path).expanduser().resolve()
        env, _, _ = build_fabric_env(fabric_samples)

        result = query_chaincode(
            env,
            CHANNEL_NAME,
            CHAINCODE_NAME,
            "GetEvidenceHistory",
            [event_id],
        )

        history = json.loads(result) if result else []
        return JSONResponse({"history": history})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/workorder/create")
async def api_create_workorder(request: Request):
    """Create rectification workorder."""
    try:
        data = await request.json()
        result = create_workorder(
            violation_id=data["violationId"],
            description=data["description"],
            assigned_org=data["assignedOrg"],
            deadline=int(data["deadline"]),
        )
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/workorder/submit")
async def api_submit_rectification(request: Request):
    """Submit rectification proof."""
    try:
        data = await request.json()
        result = submit_rectification(
            order_id=data["orderId"],
            rectification_proof=data["proof"],
            attachments=data.get("attachments", []),
        )
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/workorder/confirm")
async def api_confirm_rectification(request: Request):
    """Confirm or reject rectification."""
    try:
        data = await request.json()
        result = confirm_rectification(
            order_id=data["orderId"],
            approved=data["approved"],
            comments=data.get("comments", ""),
        )
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/workorder/overdue")
def api_query_overdue(org: Optional[str] = None, page: int = 1, limit: int = 20):
    """Query overdue workorders."""
    result = query_overdue_workorders(org, page, limit)
    return JSONResponse(result)


@app.get("/api/workorder/{order_id}")
def api_get_workorder(order_id: str):
    """Get workorder by ID."""
    try:
        result = query_workorder_by_id(order_id)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/audit/export/{batch_id}")
def api_export_audit(batch_id: str):
    """Export audit trail."""
    try:
        result = export_audit_trail(batch_id)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/config")
def api_get_config():
    """Get Fabric configuration."""
    return JSONResponse(get_fabric_config())


# Start detection loop in background
merkle_manager = MerkleBatchManager(window_seconds=SETTINGS.merkle_batch_window_seconds)

aggregate_config = {
    "min_frames": SETTINGS.aggregate_min_frames,
    "max_missed_frames": SETTINGS.aggregate_max_missed_frames,
    "iou_threshold": SETTINGS.aggregate_iou_threshold,
    "window_seconds": SETTINGS.aggregate_window_seconds,
}

detection_thread = threading.Thread(
    target=start_detection_loop,
    args=(
        model,
        video_source,
        CONFIDENCE_THRESHOLD,
        ROAD_TARGET_CLASS_IDS,
        DEVICE,
        frame_buffer,
        lock,
        merkle_manager,
        aggregate_config,
    ),
    daemon=True,
)
detection_thread.start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
