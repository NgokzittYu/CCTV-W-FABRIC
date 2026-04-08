import asyncio
import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

import cv2
import torch
from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from ultralytics import YOLO
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import SETTINGS
from services.detection_service import MerkleBatchManager, start_detection_loop
from services.fabric_client import build_fabric_env, get_fabric_config, query_chaincode
from services.merkle_utils import apply_merkle_proof
from services.gateway_service import GatewayService
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

# CORS — allow frontend dev server at :5173
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


# Pydantic model for device report validation
class DeviceReport(BaseModel):
    device_id: str
    segment_root: str
    timestamp: str
    semantic_summaries: list[str] = []
    gop_count: int


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
                frame_data = frame_buffer.get("ann" if stream_type == "ann" else "raw")
            if frame_data:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + frame_data + b"\r\n")
            time.sleep(0.03)

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

    # Try to get event data from local file first
    event_data = None
    merkle_info = None

    if json_path.exists():
        event_data = json.loads(json_path.read_text(encoding="utf-8"))
        merkle_info = event_data.get("_merkle")

    # If local file doesn't exist or has no merkle info, search in batch files
    if not merkle_info:
        # Search for the event in batch files
        batches_dir = EVIDENCE_DIR / "batches"
        if batches_dir.exists():
            for batch_file in batches_dir.rglob("batch_*.json"):
                try:
                    batch_data = json.loads(batch_file.read_text(encoding="utf-8"))
                    for event in batch_data.get("events", []):
                        if event.get("event_id") == event_id:
                            # Found the event in batch, reconstruct merkle info
                            merkle_info = {
                                "proof": event.get("proof", []),
                                "merkleRoot": batch_data.get("merkle_root", ""),
                                "batchId": batch_data.get("batch_id", ""),
                                "txId": batch_data.get("tx_id", ""),
                                "blockNumber": batch_data.get("block_number"),
                                "timestamp": batch_data.get("timestamp"),
                            }
                            # Get evidence hash from event or query chain
                            if not event_data:
                                event_data = {"evidence_hash": event.get("evidence_hash", "")}
                            break
                except Exception as e:
                    continue
                if merkle_info:
                    break

    if not merkle_info:
        return JSONResponse({
            "status": "error",
            "message": "未上链/不存在 (Event not found in batches)"
        }, status_code=404)

    evidence_hash = event_data.get("evidence_hash", "")
    proof = merkle_info.get("proof", [])
    expected_root = merkle_info.get("merkleRoot", "")
    batch_id = merkle_info.get("batchId", "")
    tx_id = merkle_info.get("txId", "")
    block_number = merkle_info.get("blockNumber")
    timestamp = merkle_info.get("timestamp")

    computed_root = apply_merkle_proof(evidence_hash, proof)
    verified = computed_root == expected_root

    # Query on-chain evidence to get chain hash
    chain_hash = ""
    try:
        fabric_samples = Path(SETTINGS.fabric_samples_path).expanduser().resolve()
        env, _, _ = build_fabric_env(fabric_samples)
        result = query_chaincode(
            env,
            CHANNEL_NAME,
            CHAINCODE_NAME,
            "ReadEvidence",
            [event_id],
        )
        if result:
            chain_evidence = json.loads(result)
            chain_hash = chain_evidence.get("evidenceHash", "")
    except Exception as e:
        print(f"[WARN] Failed to query chain hash: {e}")

    return JSONResponse({
        "status": "success" if verified else "failed",
        "verified": verified,
        "match": verified,  # Frontend expects 'match' field
        "local_hash": evidence_hash,
        "chain_hash": chain_hash,
        "proof_root": computed_root,
        "expected_root": expected_root,
        "batch_id": batch_id,
        "tx_id": tx_id,
        "block_number": block_number,
        "onchain_time": timestamp,
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


@app.post("/api/audit/verify")
async def api_verify_audit_report(request: Request):
    """Verify audit report signature via chaincode VerifyEvent."""
    try:
        data = await request.json()
        batch_id = data.get("batchId", "").strip()
        event_hash = data.get("eventHash", "").strip()
        merkle_proof_json = data.get("merkleProofJSON", "").strip()
        merkle_root = data.get("merkleRoot", "").strip()

        if not all([batch_id, event_hash, merkle_proof_json, merkle_root]):
            return JSONResponse(
                {"verified": False, "message": "缺少必要参数：batchId、eventHash、merkleProofJSON、merkleRoot"},
                status_code=400,
            )

        fabric_samples = Path(SETTINGS.fabric_samples_path).expanduser().resolve()
        env, _, _ = build_fabric_env(fabric_samples)

        result = query_chaincode(
            env,
            CHANNEL_NAME,
            CHAINCODE_NAME,
            "VerifyEvent",
            [batch_id, event_hash, merkle_proof_json, merkle_root],
        )

        verified = result.strip().lower() == "true"
        return JSONResponse({
            "verified": verified,
            "batchId": batch_id,
            "message": "报告签名验证通过" if verified else "报告签名验证失败，数据可能已被篡改",
        })
    except Exception as e:
        return JSONResponse({"verified": False, "message": str(e)}, status_code=500)


@app.get("/api/ledger/recent")
def api_get_recent_blocks():
    """Get recent blockchain batches."""
    try:
        batches_dir = EVIDENCE_DIR / "batches"
        if not batches_dir.exists():
            return JSONResponse({"blocks": []})

        # Read all batch files and sort by block number
        batch_files = list(batches_dir.rglob("batch_*.json"))
        blocks = []
        for bf in batch_files:
            try:
                data = json.loads(bf.read_text(encoding="utf-8"))
                block_number = data.get("block_number")
                # Skip batches without block number
                if block_number is None:
                    continue
                blocks.append({
                    "batch_id": data.get("batch_id", ""),
                    "block_number": block_number,
                    "tx_id": data.get("tx_id", ""),
                    "merkle_root": data.get("merkle_root", ""),
                    "event_count": data.get("event_count", len(data.get("events", []))),
                    "timestamp": data.get("timestamp", 0)
                })
            except Exception as e:
                print(f"[WARN] Failed to read batch file {bf}: {e}")
                continue

        # Sort by block number (descending) and return top 20
        blocks.sort(key=lambda b: b["block_number"], reverse=True)
        return JSONResponse({"blocks": blocks[:20]})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/batch/{batch_id}")
def api_get_batch_details(batch_id: str):
    """Get batch details with enriched event information."""
    try:
        # Find batch file
        batches_dir = EVIDENCE_DIR / "batches"
        batch_file = None
        for bf in batches_dir.rglob(f"{batch_id}.json"):
            batch_file = bf
            break

        if not batch_file or not batch_file.exists():
            return JSONResponse({"error": "Batch not found"}, status_code=404)

        batch_data = json.loads(batch_file.read_text(encoding="utf-8"))

        # Enrich events with type information
        enriched_events = []
        for event in batch_data.get("events", []):
            event_id = event.get("event_id")
            event_json_path = EVIDENCE_DIR / f"{event_id}.json"

            event_info = {
                "event_id": event_id,
                "evidence_hash": event.get("evidence_hash", ""),
                "leaf_index": event.get("leaf_index", 0),
                "type": "unknown",
                "detection_count": 0
            }

            event_data = None

            # Try to read from local file first
            if event_json_path.exists():
                try:
                    event_data = json.loads(event_json_path.read_text(encoding="utf-8"))
                except Exception as e:
                    print(f"[WARN] Failed to read local event {event_id}: {e}")

            # If local file doesn't exist, try to query from blockchain
            if not event_data:
                try:
                    fabric_samples = Path(SETTINGS.fabric_samples_path).expanduser().resolve()
                    env, _, _ = build_fabric_env(fabric_samples)
                    result = query_chaincode(
                        env,
                        CHANNEL_NAME,
                        CHAINCODE_NAME,
                        "ReadEvidence",
                        [event_id],
                    )
                    if result:
                        event_data = json.loads(result)
                except Exception as e:
                    print(f"[WARN] Failed to query event {event_id} from chain: {e}")

            # Extract type and detection count from event data
            if event_data:
                # Try multiple possible field names for event type
                event_type = event_data.get("top_class") or event_data.get("event_type") or event_data.get("type")
                if event_type:
                    # Extract class name from event_type like "detection_car" -> "car"
                    if isinstance(event_type, str) and event_type.startswith("detection_"):
                        event_info["type"] = event_type.replace("detection_", "")
                    else:
                        event_info["type"] = str(event_type)
                detections = event_data.get("detections", [])
                event_info["detection_count"] = len(detections)

            enriched_events.append(event_info)

        return JSONResponse({
            "status": "success",
            "batch_id": batch_data.get("batch_id"),
            "block_number": batch_data.get("block_number"),
            "tx_id": batch_data.get("tx_id"),
            "merkle_root": batch_data.get("merkle_root"),
            "timestamp": batch_data.get("timestamp"),
            "event_count": batch_data.get("event_count"),
            "events": enriched_events
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/config")
def api_get_config():
    """Get Fabric configuration."""
    return JSONResponse(get_fabric_config())


# ============================================================================
# Video Evidence API (Phase 1)
# ============================================================================

from services.video_store import (
    insert_video,
    insert_video_gops,
    list_videos,
    get_video,
    get_video_gops,
    insert_verify_record,
    list_verify_history,
)

UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@app.post("/api/video/upload")
async def api_video_upload(
    file: UploadFile = File(...),
    device_id: str = "cctv-default-01",
):
    """Upload video → GOP split → VIF/SHA-256 → Merkle tree → Fabric anchor."""
    try:
        # 1. Save uploaded file
        video_id = f"vid-{uuid.uuid4().hex[:12]}"
        suffix = Path(file.filename or "video.mp4").suffix
        save_path = UPLOAD_DIR / f"{video_id}{suffix}"
        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        file_size = save_path.stat().st_size

        # 2. GOP split (runs in thread to avoid blocking)
        from services.gop_splitter import split_gops
        gops = await asyncio.to_thread(split_gops, str(save_path))

        if not gops:
            return JSONResponse({"error": "GOP 切分失败，视频可能损坏"}, status_code=400)

        # 3. Build Merkle tree from GOPs
        from services.merkle_utils import build_merkle_root_and_proofs
        merkle_root, proofs = build_merkle_root_and_proofs(gops)

        # 4. Sign & anchor to Fabric
        from services.crypto_utils import build_batch_signature_material

        batch_id = f"batch-{video_id}"
        event_ids = [f"{video_id}-gop{g.gop_id}" for g in gops]
        event_hashes = [g.sha256_hash for g in gops]

        cert_path = Path(SETTINGS.device_cert_path)
        key_path = Path(SETTINGS.device_key_path)
        sign_algo = SETTINGS.device_sign_algo
        sig_required = SETTINGS.device_signature_required

        cert_pem, signature_b64, payload_hash = build_batch_signature_material(
            batch_id, device_id, merkle_root,
            int(time.time()), int(time.time()),
            event_ids, event_hashes,
            cert_path, key_path, sign_algo, sig_required,
        )

        # 5. Invoke chaincode
        tx_id = ""
        block_number = None
        try:
            from services.fabric_client import invoke_chaincode, get_latest_block_number
            fabric_samples = Path(SETTINGS.fabric_samples_path).expanduser().resolve()
            env, orderer_ca, org2_tls = build_fabric_env(fabric_samples)

            result = invoke_chaincode(
                env, orderer_ca, org2_tls,
                CHANNEL_NAME, CHAINCODE_NAME,
                "CreateEvidenceBatch",
                [
                    batch_id, device_id, merkle_root,
                    str(int(time.time())),
                    json.dumps(event_ids),
                    json.dumps(event_hashes),
                    cert_pem, signature_b64, payload_hash,
                ],
            )
            tx_id = result.get("tx_id", "")
            block_number = get_latest_block_number(env, CHANNEL_NAME)
        except Exception as e:
            print(f"[WARN] Fabric anchor failed (non-fatal): {e}")
            tx_id = f"offline-{uuid.uuid4().hex[:8]}"

        # 6. Write to SQLite
        video_rec = insert_video(
            video_id=video_id,
            device_id=device_id,
            filename=file.filename or "unknown",
            file_size=file_size,
            gop_count=len(gops),
            merkle_root=merkle_root,
            tx_id=tx_id,
            block_number=block_number,
        )

        gop_records = [
            {
                "video_id": video_id,
                "gop_index": g.gop_id,
                "sha256": g.sha256_hash,
                "vif": g.vif,
                "start_time": g.start_time,
                "end_time": g.end_time,
                "frame_count": g.frame_count,
                "byte_size": g.byte_size,
            }
            for g in gops
        ]
        insert_video_gops(video_id, gop_records)

        return JSONResponse({
            "status": "success",
            "video_id": video_id,
            "filename": file.filename,
            "gop_count": len(gops),
            "merkle_root": merkle_root,
            "tx_id": tx_id,
            "block_number": block_number,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/video/list")
def api_video_list():
    """List all archived videos."""
    videos = list_videos()
    return JSONResponse({"videos": videos})


@app.get("/api/video/{video_id}/certificate")
def api_video_certificate(video_id: str):
    """Get video evidence certificate details."""
    video = get_video(video_id)
    if not video:
        return JSONResponse({"error": "Video not found"}, status_code=404)

    gops = get_video_gops(video_id)
    return JSONResponse({
        "status": "success",
        **video,
        "gops": gops,
    })


@app.post("/api/video/verify")
async def api_video_verify(
    file: UploadFile = File(...),
    original_video_id: str = "",
):
    """Verify uploaded video against original evidence."""
    try:
        if not original_video_id:
            return JSONResponse({"error": "必须指定 original_video_id"}, status_code=400)

        # 1. Check original exists
        original = get_video(original_video_id)
        if not original:
            return JSONResponse({"error": "原始视频不存在"}, status_code=404)

        original_gops = get_video_gops(original_video_id)
        if not original_gops:
            return JSONResponse({"error": "原始 GOP 记录不存在"}, status_code=404)

        # 2. Save uploaded file
        suffix = Path(file.filename or "video.mp4").suffix
        tmp_path = UPLOAD_DIR / f"verify-{uuid.uuid4().hex[:8]}{suffix}"
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # 3. GOP split the uploaded file
        from services.gop_splitter import split_gops
        curr_gops = await asyncio.to_thread(split_gops, str(tmp_path))

        # 4. Compare GOPs using TriStateVerifier
        from services.tri_state_verifier import TriStateVerifier
        verifier = TriStateVerifier()

        gop_results = []
        worst_status = "INTACT"
        max_risk = 0.0
        status_priority = {"INTACT": 0, "RE_ENCODED": 1, "TAMPERED": 2}

        compare_count = min(len(original_gops), len(curr_gops))
        for i in range(compare_count):
            orig = original_gops[i]
            curr = curr_gops[i] if i < len(curr_gops) else None

            if curr is None:
                gop_results.append({
                    "gop_index": i,
                    "status": "TAMPERED",
                    "risk": 1.0,
                    "detail": "GOP 缺失",
                })
                worst_status = "TAMPERED"
                max_risk = 1.0
                continue

            status, risk, details = verifier.verify(
                orig["sha256"], curr.sha256_hash,
                orig.get("vif"), curr.vif,
            )
            gop_results.append({
                "gop_index": i,
                "status": status,
                "risk": round(risk, 4),
                "detail": details.get("state_desc", status),
            })
            if status_priority.get(status, 0) > status_priority.get(worst_status, 0):
                worst_status = status
            max_risk = max(max_risk, risk)

        # Handle GOP count mismatch
        if len(curr_gops) != len(original_gops):
            for i in range(compare_count, max(len(original_gops), len(curr_gops))):
                gop_results.append({
                    "gop_index": i,
                    "status": "TAMPERED",
                    "risk": 1.0,
                    "detail": "GOP 数量不匹配",
                })
            if worst_status != "TAMPERED":
                worst_status = "TAMPERED" if abs(len(curr_gops) - len(original_gops)) > 1 else "RE_ENCODED"
            max_risk = max(max_risk, 0.8)

        # 5. Save verify history
        record = insert_verify_record(
            original_video_id=original_video_id,
            uploaded_filename=file.filename or "unknown",
            overall_status=worst_status,
            overall_risk=round(max_risk, 4),
            gop_results=gop_results,
        )

        # Cleanup temp file
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

        return JSONResponse({
            "status": "success",
            "verify_id": record["id"],
            "overall_status": worst_status,
            "overall_risk": round(max_risk, 4),
            "original_gop_count": len(original_gops),
            "current_gop_count": len(curr_gops),
            "gop_results": gop_results,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/video/verify/history")
def api_verify_history(limit: int = 50):
    """Get verification history."""
    history = list_verify_history(limit)
    return JSONResponse({"history": history})


# ============================================================================
# Gateway Service Routes
# ============================================================================

@app.post("/report")
async def receive_device_report(report: DeviceReport):
    """Receive SegmentRoot report from edge device."""
    await gateway_service.add_device_report(report.model_dump())
    return {"status": "received", "device_id": report.device_id}


@app.get("/epochs")
async def list_epochs(limit: int = 20):
    """List recent epochs for debugging and demo purposes."""
    epochs = await asyncio.to_thread(gateway_service.list_epochs, limit)
    return {"epochs": epochs}


@app.get("/epoch/{epoch_id}")
async def get_epoch_info(epoch_id: str):
    """Get epoch aggregation details."""
    epoch_data = await asyncio.to_thread(gateway_service.get_epoch, epoch_id)
    if not epoch_data:
        raise HTTPException(status_code=404, detail="Epoch not found")
    return epoch_data


@app.get("/proof/{epoch_id}/{device_id}")
async def get_device_proof(epoch_id: str, device_id: str):
    """Get Merkle proof for a device in an epoch."""
    proof = await asyncio.to_thread(gateway_service.get_device_proof, epoch_id, device_id)
    if not proof:
        raise HTTPException(status_code=404, detail="Proof not found")
    return proof


# ============================================================================
# Startup: Initialize Gateway Service and Scheduler
# ============================================================================

# Initialize gateway service
fabric_samples = Path(SETTINGS.fabric_samples_path).expanduser().resolve()
fabric_env, ORDERER_CA, ORG2_TLS = build_fabric_env(fabric_samples)

gateway_service = GatewayService(
    db_path="data/gateway.db",
    fabric_config={
        "env": fabric_env,
        "orderer_ca": ORDERER_CA,
        "org2_tls": ORG2_TLS,
        "channel": CHANNEL_NAME,
        "chaincode": CHAINCODE_NAME,
    }
)

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


@app.on_event("startup")
async def startup_event():
    """Initialize scheduler on startup."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(gateway_service.flush_epoch, 'interval', seconds=30)
    scheduler.start()
    app.state.scheduler = scheduler


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup scheduler on shutdown."""
    if hasattr(app.state, 'scheduler'):
        app.state.scheduler.shutdown()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
