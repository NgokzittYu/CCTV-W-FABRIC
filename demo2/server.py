"""SecureLens Backend — GOP-level video integrity + Fabric anchoring.

Updated: Phase 1-4 integration
- Removed old MerkleBatchManager (event-driven anchoring)
- Added /api/health with real subsystem probing
- Added IPFS integration via VideoStorage
- Added GOPVerifier API endpoint
- Added EIS/MAB adaptive anchoring
- Added auto-trigger workorder on tamper detection
- Added WebSocket tamper alert broadcast
- Added verification stats API
- Added Fabric retry wrapper
- Added real device list API
"""
import asyncio
import base64
import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import subprocess
import shutil
import threading
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlparse, urlunparse
from zoneinfo import ZoneInfo

import av
import cv2
import torch
from fastapi import FastAPI, File, HTTPException, Request, Response, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel
from ultralytics import YOLO
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config import SETTINGS
from services.detection_service import start_detection_loop, GOPAnchorManager
from services.fabric_client import (
    build_fabric_env, get_fabric_config, get_latest_block_number,
    invoke_chaincode, query_chaincode,
)
from services.merkle_utils import apply_merkle_proof
from services.gateway_service import GatewayService
from services.ipfs_storage import IPFSClient, VideoStorage
from services.gop_verifier import GOPVerifier
from services.adaptive_anchor import AdaptiveAnchor
from services.mab_anchor import MABAnchorManager, ARM_INTERVALS
from services.local_ring_buffer import LocalRingBufferManager
from services.workorder_service import (
    confirm_rectification, create_workorder, export_audit_trail,
    query_overdue_workorders, query_workorder_by_id, submit_rectification,
)
from services.video_store import (
    insert_video, insert_video_gops, list_videos,
    get_video, get_video_gops, insert_verify_record, list_verify_history,
    get_device_gops_by_time,
)

# ── Logging ──────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/securelens.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("securelens")

# ── Config ───────────────────────────────────────────────────────
EVIDENCE_DIR = SETTINGS.evidence_dir
CAMERA_ID = SETTINGS.camera_id
CHAINCODE_NAME = SETTINGS.chaincode_name
CHANNEL_NAME = SETTINGS.channel_name
CONFIDENCE_THRESHOLD = SETTINGS.confidence_threshold
ROAD_TARGET_CLASS_IDS = SETTINGS.road_target_class_ids
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
EVIDENCE_DIR.mkdir(exist_ok=True)
Path("data").mkdir(exist_ok=True)
RING_BUFFER_DIR = Path("data/ring_buffer")
MAB_STATE_PATH = Path("data/mab_state.json")
TAMPER_JOB_DIR = UPLOAD_DIR / "tamper_jobs"
TAMPER_JOB_DIR.mkdir(parents=True, exist_ok=True)
TAMPER_JOB_TTL_SECONDS = 24 * 60 * 60
TAMPER_JOB_SEGMENT_NAME = "segment.ts"
TAMPER_JOB_META_NAME = "meta.json"
TAMPER_DURATIONS_SECONDS = (2.5, 2.0, 3.0)
TAMPER_MIN_EDGE_PADDING_SECONDS = 0.2
TAMPER_MIN_GAP_SECONDS = 0.4

# Segment GOP Limits (Phase 8)
GOP_DURATION_SECONDS = float(os.environ.get("GOP_DURATION_SECONDS", "2.0"))
MIN_SEGMENT_GOPS = 5    # HIGH 活跃时最快 5 GOP 锚定一次
MAX_SEGMENT_GOPS = 150  # LOW 活跃时最慢 150 GOP 锚定一次

# ── App ──────────────────────────────────────────────────────────
app = FastAPI(title="SecureLens", description="GOP-level video integrity + Fabric anchoring")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
)

# ── Global state ─────────────────────────────────────────────────
frame_buffer: Dict[str, Optional[bytes]] = {"raw": None, "ann": None}
lock = threading.Lock()

# Connection status tracking (Phase 3)
connection_status: Dict[str, Any] = {
    "fabric_last_success": None,
    "ipfs_last_success": None,
    "stream_reconnects": 0,
    "anchor_failures": 0,
    "anchor_successes": 0,
}
detection_ws_state: Dict[str, float] = {"last_emit": 0.0}
REPLAY_MAX_RANGE_SECONDS = 30 * 60
DEFAULT_REPLAY_TIMEZONE = "Asia/Shanghai"
EXPORT_GAP_THRESHOLD_SECONDS = 0.5
EXPORT_SAMPLE_RE = re.compile(
    r"^sl__(?P<device>[A-Za-z0-9_-]+)__(?P<start>\d{8}T\d{6}\+\d{4})__"
    r"(?P<end>\d{8}T\d{6}\+\d{4})__g(?P<gops>\d+)__gap(?P<gap>[01])(?:\.[A-Za-z0-9]+)?$"
)


# ── YOLO → EIS Bridge (Phase 7) ─────────────────────────────────
class YOLOSemanticBridge:
    """Thread-safe bridge: YOLO detection thread → EIS/MAB callback.

    The YOLO detection thread calls feed() every frame with detection results.
    When a GOP arrives, the on_gop_callback calls snapshot() to obtain
    a SemanticFingerprint built from accumulated YOLO stats.
    """

    def __init__(self, window_size: int = 60):
        self._lock = threading.Lock()
        self._frame_counts: deque = deque(maxlen=window_size)
        self._class_accum: Dict[str, int] = defaultdict(int)
        self._total_accum: int = 0
        self._last_keyframe = None
        self._frames_since_snapshot: int = 0

    def feed(self, boxes, class_names: dict, raw_frame=None):
        """Called by YOLO detection thread every frame."""
        counts: Dict[str, int] = defaultdict(int)
        if boxes is not None:
            for box in boxes:
                cls_id = int(box.cls[0])
                cls_name = class_names.get(cls_id, f"class_{cls_id}")
                counts[cls_name] += 1

        total = sum(counts.values())
        with self._lock:
            self._frame_counts.append(total)
            for name, cnt in counts.items():
                self._class_accum[name] += cnt
            self._total_accum += total
            self._frames_since_snapshot += 1
            if raw_frame is not None:
                self._last_keyframe = raw_frame.copy()

    def snapshot(self, gop_id: int = 0):
        """Called by on_gop_callback: returns (SemanticFingerprint, keyframe)."""
        from services.semantic_fingerprint import SemanticFingerprint

        with self._lock:
            objects = dict(self._class_accum)
            total = self._total_accum
            keyframe = self._last_keyframe
            frames = self._frames_since_snapshot
            # Reset accumulators for next GOP
            self._class_accum.clear()
            self._total_accum = 0
            self._frames_since_snapshot = 0

        # Build deterministic JSON for semantic hash
        json_str = json.dumps(
            {"gop_id": gop_id, "objects": objects, "frames": frames},
            sort_keys=True, separators=(",", ":"),
        )
        semantic_hash = hashlib.sha256(json_str.encode("utf-8")).hexdigest()

        semantic = SemanticFingerprint(
            gop_id=gop_id,
            timestamp=datetime.now().isoformat(),
            objects=objects,
            total_count=total,
            json_str=json_str,
            semantic_hash=semantic_hash,
        )
        return semantic, keyframe

    @property
    def recent_avg(self) -> float:
        """Average object count in recent frames (for stats display)."""
        with self._lock:
            if not self._frame_counts:
                return 0.0
            return sum(self._frame_counts) / len(self._frame_counts)

yolo_bridge = YOLOSemanticBridge(window_size=60)


def _relative_gop_segment_url(device_id: str, cid: str) -> str:
    return f"/api/ipfs/segment/{cid}.ts?device_id={quote(device_id)}"


def _relative_gop_playlist_url(device_id: str, start_time: float, end_time: float) -> str:
    return (
        f"/api/ipfs/playlist.m3u8?device_id={quote(device_id)}"
        f"&start={start_time:.6f}&end={end_time:.6f}"
    )


def _relative_replay_playlist_url(
    device_id: str,
    start_local: str,
    end_local: str,
    timezone: str = DEFAULT_REPLAY_TIMEZONE,
) -> str:
    return (
        f"/api/ipfs/replay/playlist.m3u8?device_id={quote(device_id)}"
        f"&start_local={quote(start_local)}&end_local={quote(end_local)}"
        f"&timezone={quote(timezone)}"
    )


def _enrich_gop_playback_urls(device_id: str, gop: Dict[str, Any], record: Optional[Dict[str, Any]], storage: VideoStorage):
    if not record:
        return
    cid = record.get("ipfs_cid")
    if cid:
        gop["ipfs_cid"] = cid
        gop["ipfs_gateway_url"] = storage.get_gateway_url(cid)
    duration = record.get("duration_seconds")
    if duration is not None:
        gop["duration"] = duration
        if cid and storage.has_playback_metadata(record):
            start_time = gop.get("start_time", record.get("timestamp"))
            end_time = gop.get("end_time")
            if start_time is not None and end_time is not None:
                gop["playback_playlist_url"] = _relative_gop_playlist_url(device_id, start_time, end_time)
        gop["playback_segment_url"] = _relative_gop_segment_url(device_id, cid)


def _purge_previous_runtime_state() -> Dict[str, int]:
    """Drop previous live GOP/runtime state so each boot starts clean."""
    result = {
        "videos": 0,
        "video_gops": 0,
        "verify_history": 0,
        "ipfs_gops": 0,
        "uploads_removed": 0,
        "ring_buffer_removed": 0,
        "mab_state_removed": 0,
    }

    video_db_path = Path("data/video_store.db")
    ipfs_db_path = Path("data/ipfs_index.db")

    live_ids: List[str] = []
    live_sha256: List[str] = []

    if video_db_path.exists():
        conn = sqlite3.connect(str(video_db_path))
        try:
            live_ids = [
                row[0]
                for row in conn.execute(
                    "SELECT id FROM videos WHERE filename LIKE 'live_%'"
                ).fetchall()
                if row and row[0]
            ]
            live_rows = conn.execute(
                """
                SELECT g.sha256
                FROM video_gops g
                JOIN videos v ON v.id = g.video_id
                WHERE v.filename LIKE 'live_%'
                """
            ).fetchall()
            live_sha256 = list({row[0] for row in live_rows if row and row[0]})
            if live_ids:
                placeholders = ",".join("?" for _ in live_ids)
                result["verify_history"] = conn.execute(
                    f"DELETE FROM verify_history WHERE original_video_id IN ({placeholders})",
                    live_ids,
                ).rowcount
                result["video_gops"] = conn.execute(
                    f"DELETE FROM video_gops WHERE video_id IN ({placeholders})",
                    live_ids,
                ).rowcount
                result["videos"] = conn.execute(
                    f"DELETE FROM videos WHERE id IN ({placeholders})",
                    live_ids,
                ).rowcount
            conn.commit()
        finally:
            conn.close()

    if ipfs_db_path.exists() and live_sha256:
        ipfs_conn = sqlite3.connect(str(ipfs_db_path))
        try:
            for offset in range(0, len(live_sha256), 500):
                batch = live_sha256[offset:offset + 500]
                placeholders = ",".join("?" for _ in batch)
                result["ipfs_gops"] += ipfs_conn.execute(
                    f"DELETE FROM gop_index WHERE sha256_hash IN ({placeholders})",
                    batch,
                ).rowcount
            ipfs_conn.commit()
        finally:
            ipfs_conn.close()

    if UPLOAD_DIR.exists():
        for child in UPLOAD_DIR.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
            result["uploads_removed"] += 1
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    if RING_BUFFER_DIR.exists():
        for child in RING_BUFFER_DIR.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
            result["ring_buffer_removed"] += 1
    RING_BUFFER_DIR.mkdir(parents=True, exist_ok=True)

    if MAB_STATE_PATH.exists():
        MAB_STATE_PATH.unlink(missing_ok=True)
        result["mab_state_removed"] = 1

    return result


try:
    STARTUP_PURGE_RESULT = _purge_previous_runtime_state()
except Exception as exc:
    logger.warning("Failed to purge previous runtime state before startup: %s", exc)
    STARTUP_PURGE_RESULT = {
        "videos": 0,
        "video_gops": 0,
        "verify_history": 0,
        "ipfs_gops": 0,
        "uploads_removed": 0,
        "ring_buffer_removed": 0,
        "mab_state_removed": 0,
    }


def _parse_local_datetime(value: str, timezone_name: str) -> datetime:
    """Parse a wall-clock datetime string in a declared timezone."""
    normalized = (value or "").strip().replace(" ", "T")
    if not normalized:
        raise ValueError("缺少时间参数")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"无法解析时间: {value}") from exc
    tz = ZoneInfo(timezone_name or DEFAULT_REPLAY_TIMEZONE)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def _resolve_replay_range(
    start_local: str,
    end_local: str,
    timezone_name: str,
) -> tuple[float, float, str]:
    tz_name = timezone_name or DEFAULT_REPLAY_TIMEZONE
    start_dt = _parse_local_datetime(start_local, tz_name)
    end_dt = _parse_local_datetime(end_local, tz_name)
    start_ts = start_dt.timestamp()
    end_ts = end_dt.timestamp()
    if start_ts >= end_ts:
        raise ValueError("开始时间必须早于结束时间")
    if (end_ts - start_ts) > REPLAY_MAX_RANGE_SECONDS:
        raise ValueError("单次回放时间范围不能超过 30 分钟")
    return start_ts, end_ts, tz_name


def _build_playlist_response(
    storage: VideoStorage,
    device_id: str,
    start: float,
    end: float,
):
    gops = storage.list_gops(device_id, start, end)
    playable = [g for g in gops if storage.has_playback_metadata(g)]
    if not playable:
        return JSONResponse({"error": "No playable GOPs found in requested range"}, status_code=404)

    target_duration = max(
        1,
        math.ceil(max((g.get("duration_seconds") or 0.0) for g in playable)),
    )
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        "#EXT-X-PLAYLIST-TYPE:VOD",
        f"#EXT-X-TARGETDURATION:{target_duration}",
        "#EXT-X-MEDIA-SEQUENCE:0",
    ]
    for g in playable:
        duration = max(g.get("duration_seconds") or 0.0, 0.001)
        lines.append(f"#EXTINF:{duration:.3f},")
        lines.append(_relative_gop_segment_url(device_id, g["ipfs_cid"]))
    lines.append("#EXT-X-ENDLIST")
    return Response(
        content="\n".join(lines) + "\n",
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "no-store"},
    )


def _sanitize_export_device_id(device_id: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", (device_id or "").strip())
    normalized = normalized.strip("_")
    return normalized or "unknown_device"


def _format_export_timestamp(ts: float, timezone_name: str = DEFAULT_REPLAY_TIMEZONE) -> str:
    tz = ZoneInfo(timezone_name or DEFAULT_REPLAY_TIMEZONE)
    return datetime.fromtimestamp(ts, tz=tz).strftime("%Y%m%dT%H%M%S%z")


def _format_replay_label(ts: Optional[float], timezone_name: str = DEFAULT_REPLAY_TIMEZONE) -> str:
    if ts is None:
        return "—"
    tz = ZoneInfo(timezone_name or DEFAULT_REPLAY_TIMEZONE)
    return datetime.fromtimestamp(ts, tz=tz).strftime("%Y-%m-%d %H:%M:%S %z")


def _build_export_filename_base(
    device_id: str,
    actual_start: float,
    actual_end: float,
    gop_count: int,
    gap_flag: int,
    timezone_name: str = DEFAULT_REPLAY_TIMEZONE,
) -> str:
    return (
        f"sl__{_sanitize_export_device_id(device_id)}__"
        f"{_format_export_timestamp(actual_start, timezone_name)}__"
        f"{_format_export_timestamp(actual_end, timezone_name)}__"
        f"g{int(gop_count)}__gap{int(gap_flag)}"
    )


def _parse_export_sample_filename(filename: str) -> Dict[str, Any]:
    basename = Path(filename or "").name
    match = EXPORT_SAMPLE_RE.match(basename)
    if not match:
        raise ValueError("该文件不是 SecureLens 导出样本")

    start_dt = datetime.strptime(match.group("start"), "%Y%m%dT%H%M%S%z")
    end_dt = datetime.strptime(match.group("end"), "%Y%m%dT%H%M%S%z")
    return {
        "device_id": match.group("device"),
        "actual_start_time": start_dt.timestamp(),
        "actual_end_time": end_dt.timestamp(),
        "expected_gop_count": int(match.group("gops")),
        "gap_flag": int(match.group("gap")),
        "filename": basename,
    }


def _cleanup_tamper_jobs(max_age_seconds: int = TAMPER_JOB_TTL_SECONDS) -> None:
    now = time.time()
    try:
        for child in TAMPER_JOB_DIR.iterdir():
            try:
                if not child.is_dir():
                    continue
                if now - child.stat().st_mtime > max_age_seconds:
                    shutil.rmtree(child, ignore_errors=True)
            except Exception:
                continue
    except FileNotFoundError:
        TAMPER_JOB_DIR.mkdir(parents=True, exist_ok=True)


def _sanitize_tamper_job_id(job_id: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{6,64}", job_id or ""):
        raise FileNotFoundError("Tamper job not found")
    return job_id


def _tamper_job_path(job_id: str) -> Path:
    return TAMPER_JOB_DIR / _sanitize_tamper_job_id(job_id)


def _load_tamper_job_meta(job_id: str) -> tuple[Path, Dict[str, Any]]:
    _cleanup_tamper_jobs()
    job_dir = _tamper_job_path(job_id)
    meta_path = job_dir / TAMPER_JOB_META_NAME
    if not meta_path.exists():
        raise FileNotFoundError("Tamper job not found")
    with meta_path.open("r", encoding="utf-8") as f:
        return job_dir, json.load(f)


def _write_tamper_job_meta(job_dir: Path, payload: Dict[str, Any]) -> None:
    with (job_dir / TAMPER_JOB_META_NAME).open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _probe_video_duration(video_path: Path) -> float:
    with av.open(str(video_path)) as container:
        stream = next((s for s in container.streams if s.type == "video"), None)
        if stream and stream.duration is not None and stream.time_base is not None:
            return max(float(stream.duration * stream.time_base), 0.0)
        if container.duration is not None:
            return max(float(container.duration) / 1_000_000.0, 0.0)
    raise ValueError("无法探测视频时长")


def _select_tamper_windows(duration_seconds: float, replace_seconds: float) -> Dict[str, float]:
    if duration_seconds <= 0 or replace_seconds <= 0:
        raise ValueError("视频时长无效")

    edge = TAMPER_MIN_EDGE_PADDING_SECONDS
    min_gap = TAMPER_MIN_GAP_SECONDS
    min_required = (2 * replace_seconds) + min_gap + (2 * edge)
    if duration_seconds < min_required:
        raise ValueError(
            f"样本时长不足以执行 {replace_seconds:.1f}s 替帧篡改"
        )

    source_start = edge
    source_end = source_start + replace_seconds
    tamper_start = max((duration_seconds * 0.55) - (replace_seconds / 2.0), source_end + min_gap)
    tamper_start = min(tamper_start, duration_seconds - replace_seconds - edge)
    tamper_end = tamper_start + replace_seconds

    if tamper_start < source_end + min_gap or tamper_end > duration_seconds - edge + 1e-6:
        raise ValueError(
            f"样本时长不足以执行 {replace_seconds:.1f}s 替帧篡改"
        )

    return {
        "source_start": round(source_start, 6),
        "source_end": round(source_end, 6),
        "tamper_start": round(tamper_start, 6),
        "tamper_end": round(tamper_end, 6),
        "replace_seconds": round(replace_seconds, 6),
        "duration_seconds": round(duration_seconds, 6),
    }


def _run_frame_replace_tamper(
    src_path: Path,
    output_path: Path,
    replace_seconds: float,
    *,
    target_gop_seconds: Optional[float] = None,
) -> Dict[str, float]:
    duration_seconds = _probe_video_duration(src_path)
    windows = _select_tamper_windows(duration_seconds, replace_seconds)
    filter_complex = (
        f"[0:v]trim=start=0:end={windows['tamper_start']:.6f},setpts=PTS-STARTPTS[v0];"
        f"[0:v]trim=start={windows['source_start']:.6f}:end={windows['source_end']:.6f},setpts=PTS-STARTPTS[v1];"
        f"[0:v]trim=start={windows['tamper_end']:.6f},setpts=PTS-STARTPTS[v2];"
        "[v0][v1][v2]concat=n=3:v=1:a=0[v]"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(src_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-pix_fmt",
        "yuv420p",
    ]
    if target_gop_seconds and target_gop_seconds > 0:
        # Keep re-encoded tamper samples close to the source GOP cadence so
        # downstream GOP-level verification can still observe multiple GOPs.
        cmd.extend([
            "-force_key_frames",
            f"expr:gte(t,n_forced*{target_gop_seconds:.6f})",
            "-sc_threshold",
            "0",
        ])
    cmd.extend([
        "-f",
        "mpegts",
        str(output_path),
    ])
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "").strip() or "ffmpeg 替帧篡改失败"
        raise RuntimeError(message)
    if not output_path.exists() or output_path.stat().st_size <= 0:
        raise RuntimeError("篡改样本生成失败")
    return windows


def _build_tamper_playlist_response(job_id: str, duration_seconds: float) -> Response:
    target_duration = max(1, math.ceil(max(duration_seconds, 0.001)))
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        "#EXT-X-PLAYLIST-TYPE:VOD",
        f"#EXT-X-TARGETDURATION:{target_duration}",
        "#EXT-X-MEDIA-SEQUENCE:0",
        f"#EXTINF:{max(duration_seconds, 0.001):.3f},",
        f"/api/video/tamper/jobs/{quote(job_id)}/segment.ts",
        "#EXT-X-ENDLIST",
    ]
    return Response(
        content="\n".join(lines) + "\n",
        media_type="application/vnd.apple.mpegurl",
        headers={"Cache-Control": "no-store"},
    )


def _build_replay_export_payload(
    storage: VideoStorage,
    device_id: str,
    start: float,
    end: float,
    *,
    timezone_name: str = DEFAULT_REPLAY_TIMEZONE,
    requested_start_local: Optional[str] = None,
    requested_end_local: Optional[str] = None,
) -> Dict[str, Any]:
    gops = storage.list_gops(device_id, start, end)
    playable = [g for g in gops if storage.has_playback_metadata(g)]
    if not playable:
        raise FileNotFoundError("No playable GOPs found in requested range")

    playable.sort(key=lambda item: (item.get("timestamp") or 0.0, item.get("gop_id") or 0))
    first_start = float(playable[0].get("timestamp") or 0.0)
    actual_start = first_start
    actual_end = first_start + max(float(playable[0].get("duration_seconds") or 0.0), 0.0)
    playable_duration = 0.0
    gaps: List[Dict[str, float]] = []
    previous_end = actual_end

    manifest_gops = []
    for index, gop in enumerate(playable):
        start_time = float(gop.get("timestamp") or 0.0)
        duration = max(float(gop.get("duration_seconds") or 0.0), 0.0)
        end_time = start_time + duration
        if index > 0 and (start_time - previous_end) > EXPORT_GAP_THRESHOLD_SECONDS:
            gaps.append({
                "start_ts": previous_end,
                "end_ts": start_time,
                "duration_seconds": round(start_time - previous_end, 6),
            })
        previous_end = max(previous_end, end_time)
        actual_end = max(actual_end, end_time)
        playable_duration += duration
        manifest_gops.append({
            "gop_id": gop.get("gop_id"),
            "timestamp": start_time,
            "end_time": end_time,
            "duration_seconds": duration,
            "ipfs_cid": gop.get("ipfs_cid"),
            "sha256_hash": gop.get("sha256_hash"),
        })

    gap_flag = 1 if gaps else 0
    filename_base = _build_export_filename_base(
        device_id,
        actual_start,
        actual_end,
        len(playable),
        gap_flag,
        timezone_name,
    )
    manifest = {
        "version": 1,
        "device_id": device_id,
        "timezone": timezone_name,
        "download_format": "mpegts",
        "filename_base": filename_base,
        "requested_range": {
            "start_local": requested_start_local or _format_replay_label(start, timezone_name),
            "end_local": requested_end_local or _format_replay_label(end, timezone_name),
            "start_ts": start,
            "end_ts": end,
        },
        "exported_range": {
            "start_local": _format_replay_label(actual_start, timezone_name),
            "end_local": _format_replay_label(actual_end, timezone_name),
            "start_ts": actual_start,
            "end_ts": actual_end,
        },
        "continuous": gap_flag == 0,
        "gap_count": len(gaps),
        "playable_duration_seconds": round(playable_duration, 6),
        "gop_count": len(playable),
        "gops": manifest_gops,
        "gaps": gaps,
    }
    return {
        "playable_gops": playable,
        "actual_start_time": actual_start,
        "actual_end_time": actual_end,
        "gap_flag": gap_flag,
        "gap_count": len(gaps),
        "playable_duration_seconds": playable_duration,
        "filename_base": filename_base,
        "manifest": manifest,
    }


def _build_reference_gops_for_export(
    storage: VideoStorage,
    device_id: str,
    start: float,
    end: float,
) -> List[Dict[str, Any]]:
    payload = _build_replay_export_payload(storage, device_id, start, end)
    stored_rows = get_device_gops_by_time(device_id, start, end)
    rows_by_sha = {row.get("sha256"): row for row in stored_rows if row.get("sha256")}
    reference_gops = []
    for index, gop in enumerate(payload["playable_gops"]):
        sha256 = gop.get("sha256_hash", "")
        matched = rows_by_sha.get(sha256, {})
        reference_gops.append({
            "gop_index": index,
            "sha256": sha256,
            "vif": matched.get("vif"),
            "start_time": gop.get("timestamp"),
            "end_time": (gop.get("timestamp") or 0.0) + max(gop.get("duration_seconds") or 0.0, 0.0),
            "ipfs_cid": gop.get("ipfs_cid"),
            "source_video_id": matched.get("video_id"),
            "source_gop_index": matched.get("gop_index"),
        })
    return reference_gops


def _compare_gop_sequences(reference_gops: List[Dict[str, Any]], current_gops: List[Any]) -> tuple[List[Dict[str, Any]], str, float]:
    from services.tri_state_verifier import TriStateVerifier

    verifier = TriStateVerifier()
    gop_results: List[Dict[str, Any]] = []
    worst = "INTACT"
    max_risk = 0.0
    priorities = {"INTACT": 0, "RE_ENCODED": 1, "TAMPERED": 2}
    count = min(len(reference_gops), len(current_gops))

    for index in range(count):
        original = reference_gops[index]
        current = current_gops[index] if index < len(current_gops) else None
        if current is None:
            gop_results.append({"gop_index": index, "status": "TAMPERED", "risk": 1.0, "detail": "GOP 缺失"})
            worst, max_risk = "TAMPERED", 1.0
            continue
        status, risk, detail = verifier.verify(
            original.get("sha256", ""),
            current.sha256_hash,
            original.get("vif"),
            current.vif,
        )
        gop_results.append({
            "gop_index": index,
            "status": status,
            "risk": round(risk, 4),
            "detail": detail.get("state_desc", status),
            "reference_hash": original.get("sha256", ""),
            "current_hash": current.sha256_hash,
        })
        if priorities.get(status, 0) > priorities.get(worst, 0):
            worst = status
        max_risk = max(max_risk, risk)

    if len(current_gops) != len(reference_gops):
        for index in range(count, max(len(reference_gops), len(current_gops))):
            gop_results.append({"gop_index": index, "status": "TAMPERED", "risk": 1.0, "detail": "GOP 数量不匹配"})
        if worst != "TAMPERED":
            worst = "TAMPERED" if abs(len(current_gops) - len(reference_gops)) > 1 else "RE_ENCODED"
        max_risk = max(max_risk, 0.8)

    return gop_results, worst, max_risk


def _align_reference_gops_for_export_verify(
    reference_gops: List[Dict[str, Any]],
    current_gops: List[Any],
    *,
    expected_gop_count: int = 0,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], str, float]:
    """
    Export filenames only keep second-level timestamps. When the true replay
    window starts/ends inside a second, rebuilding the reference set later can
    include 1-2 extra overlapping GOPs at the boundaries. Try contiguous
    windows and keep the best alignment for the uploaded TS sample.
    """
    if not reference_gops:
        return reference_gops, [], "TAMPERED", 1.0

    candidate_lengths = []
    reference_count = len(reference_gops)
    boundary_tolerance = 2
    for value in (expected_gop_count, reference_count):
        if value > 0 and value <= reference_count and value not in candidate_lengths:
            candidate_lengths.append(value)
    current_count = len(current_gops)
    if (
        current_count > 0
        and current_count <= reference_count
        and current_count not in candidate_lengths
        and (
            abs(current_count - expected_gop_count) <= boundary_tolerance
            or abs(current_count - reference_count) <= boundary_tolerance
        )
    ):
        candidate_lengths.append(current_count)
    if not candidate_lengths:
        candidate_lengths = [reference_count]

    priorities = {"INTACT": 0, "RE_ENCODED": 1, "TAMPERED": 2}
    best_candidate = None

    for candidate_length in candidate_lengths:
        max_offset = len(reference_gops) - candidate_length
        for offset in range(max_offset + 1):
            candidate = reference_gops[offset:offset + candidate_length]
            gop_results, worst, max_risk = _compare_gop_sequences(candidate, current_gops)
            non_intact = sum(1 for item in gop_results if item.get("status") != "INTACT")
            score = (
                priorities.get(worst, 3),
                non_intact,
                abs(candidate_length - len(current_gops)),
                round(max_risk, 6),
                offset,
            )
            if best_candidate is None or score < best_candidate["score"]:
                best_candidate = {
                    "reference_gops": candidate,
                    "gop_results": gop_results,
                    "worst": worst,
                    "max_risk": max_risk,
                    "score": score,
                }
                if score[0] == 0 and score[1] == 0 and score[2] == 0 and score[3] == 0:
                    break
        if best_candidate and best_candidate["score"][:4] == (0, 0, 0, 0):
            break

    assert best_candidate is not None
    return (
        best_candidate["reference_gops"],
        best_candidate["gop_results"],
        best_candidate["worst"],
        best_candidate["max_risk"],
    )


async def _finalize_verify_outcome(
    original_video_id: str,
    uploaded_filename: str,
    worst: str,
    max_risk: float,
    gop_results: List[Dict[str, Any]],
    *,
    verify_mode: str = "original_video",
    reference_device_id: Optional[str] = None,
    reference_start_time: Optional[float] = None,
    reference_end_time: Optional[float] = None,
    gap_flag: int = 0,
    matched_gop_count: int = 0,
    workorder_subject: Optional[str] = None,
    broadcast_video_id: Optional[str] = None,
) -> tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    rec = insert_verify_record(
        original_video_id,
        uploaded_filename,
        worst,
        round(max_risk, 4),
        gop_results,
        verify_mode=verify_mode,
        reference_device_id=reference_device_id,
        reference_start_time=reference_start_time,
        reference_end_time=reference_end_time,
        gap_flag=gap_flag,
        matched_gop_count=matched_gop_count,
    )

    wo_result = None
    if worst == "TAMPERED" or max_risk > 0.8:
        try:
            subject = workorder_subject or f"视频 {original_video_id} 完整性验证异常"
            wo_result = create_workorder(
                f"tamper-{rec['id']}",
                f"{subject} (状态={worst}, 风险={max_risk:.1%}, "
                f"异常GOP={sum(1 for r in gop_results if r['status'] != 'INTACT')}/{len(gop_results)})",
                "Org1MSP",
                int(time.time()) + 86400,
            )
            logger.warning(f"[TAMPER] Auto workorder created for {original_video_id}: {worst}")
        except Exception as e:
            logger.warning(f"[TAMPER] Auto workorder failed: {e}")

    if worst != "INTACT":
        try:
            await ws_manager.broadcast({
                "type": "tamper_alert",
                "video_id": broadcast_video_id or original_video_id,
                "status": worst,
                "risk": round(max_risk, 4),
                "affected_gops": sum(1 for r in gop_results if r["status"] != "INTACT"),
                "total_gops": len(gop_results),
                "timestamp": int(time.time()),
                "workorder_id": wo_result.get("orderId") if wo_result else None,
            })
        except Exception as e:
            logger.warning(f"[WS] Tamper alert broadcast failed: {e}")

    return rec, wo_result


def _build_batch_from_video(video: Dict[str, Any]) -> Dict[str, Any]:
    video_id = str(video.get("id", "") or "")
    gops = get_video_gops(video_id)
    window_start = min((g.get("start_time") or video.get("created_at") or 0) for g in gops) if gops else (video.get("created_at") or 0)
    window_end = max((g.get("end_time") or video.get("created_at") or 0) for g in gops) if gops else (video.get("created_at") or 0)
    events = [
        {
            "event_id": f"{video_id}-gop{g.get('gop_index')}",
            "evidence_hash": g.get("sha256", ""),
            "leaf_index": idx,
            "proof": [],
            "vif": g.get("vif", ""),
            "start_time": g.get("start_time"),
            "end_time": g.get("end_time"),
            "frame_count": g.get("frame_count"),
            "byte_size": g.get("byte_size"),
        }
        for idx, g in enumerate(gops)
    ]
    return {
        "batch_id": f"batch-{video_id}",
        "device_id": video.get("device_id", ""),
        "camera_id": video.get("device_id", ""),
        "video_id": video_id,
        "merkle_root": video.get("merkle_root", ""),
        "window_start": window_start,
        "window_end": window_end,
        "tx_id": video.get("tx_id", ""),
        "block_number": video.get("block_number"),
        "timestamp": video.get("created_at", 0),
        "event_count": video.get("gop_count", len(events)),
        "events": events,
    }


def _load_batch_details(include_video_store: bool = True) -> List[Dict[str, Any]]:
    batch_map: Dict[str, Dict[str, Any]] = {}
    batches_dir = EVIDENCE_DIR / "batches"

    if batches_dir.exists():
        for bf in batches_dir.rglob("batch_*.json"):
            try:
                batch = json.loads(bf.read_text(encoding="utf-8"))
                batch_id = str(batch.get("batch_id", "") or "")
                if batch_id:
                    batch_map[batch_id] = batch
            except Exception:
                continue

    if include_video_store:
        for video in list_videos():
            if video.get("block_number") is None:
                continue
            synthesized = _build_batch_from_video(video)
            batch_map.setdefault(synthesized["batch_id"], synthesized)

    return sorted(
        batch_map.values(),
        key=lambda item: (item.get("block_number") or -1, item.get("timestamp") or 0),
        reverse=True,
    )

# ── YOLO model ───────────────────────────────────────────────────
MODEL_CANDIDATES = SETTINGS.model_candidates
selected_model = next((m for m in MODEL_CANDIDATES if Path(m).exists()), MODEL_CANDIDATES[0])
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
logger.info(f"YOLO model: {selected_model} on {DEVICE}")
model = YOLO(selected_model)
video_source = SETTINGS.video_source
anchor_video_source = video_source
anchor_ingest_mode = "direct"
ring_buffer_manager: Optional[LocalRingBufferManager] = None

if SETTINGS.local_ring_buffer_enabled:
    try:
        ring_buffer_manager = LocalRingBufferManager(
            video_source,
            SETTINGS.local_ring_buffer_dir,
            segment_seconds=SETTINGS.local_ring_buffer_segment_seconds,
            retention_seconds=SETTINGS.local_ring_buffer_retention_seconds,
        )
        ring_buffer_manager.start()
        if ring_buffer_manager.wait_until_ready():
            anchor_video_source = str(ring_buffer_manager.playlist_path)
            anchor_ingest_mode = "buffered"
            logger.info("Using local ring buffer for GOP ingest: %s", anchor_video_source)
        else:
            logger.warning("Local ring buffer did not become ready in time, falling back to direct ingest")
            ring_buffer_manager.stop()
            ring_buffer_manager = None
    except Exception as e:
        logger.warning("Failed to initialize local ring buffer, falling back to direct ingest: %s", e)
        if ring_buffer_manager:
            ring_buffer_manager.stop()
        ring_buffer_manager = None


# ── Pydantic ─────────────────────────────────────────────────────
class DeviceReport(BaseModel):
    device_id: str
    segment_root: str
    timestamp: str
    semantic_summaries: list[str] = []
    gop_count: int


# ── WebSocket ────────────────────────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active: List[WebSocket] = []
    async def connect(self, ws: WebSocket):
        await ws.accept(); self.active.append(ws)
    def disconnect(self, ws: WebSocket):
        if ws in self.active:
            self.active.remove(ws)
    async def broadcast(self, msg: dict):
        for c in list(self.active):
            try: await c.send_json(msg)
            except Exception: pass

ws_manager = ConnectionManager()


# ── Fabric retry wrapper (Phase 3) ──────────────────────────────
def invoke_with_retry(function: str, args: list, max_retries: int = 3) -> dict:
    """Fabric chaincode invoke with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            result = invoke_chaincode(
                fabric_env, ORDERER_CA, ORG2_TLS,
                CHANNEL_NAME, CHAINCODE_NAME, function, args,
            )
            connection_status["fabric_last_success"] = time.time()
            connection_status["anchor_successes"] += 1
            return result
        except Exception as e:
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.warning(f"Fabric {function} attempt {attempt+1} failed: {e}, retrying in {wait}s")
                time.sleep(wait)
            else:
                connection_status["anchor_failures"] += 1
                logger.error(f"Fabric {function} failed after {max_retries} retries: {e}")
                return {"tx_id": f"offline-{uuid.uuid4().hex[:8]}", "error": str(e)}


# ══════════════════════════════════════════════════════════════════
# ROUTES
# ══════════════════════════════════════════════════════════════════

# ── Health (Phase 1.1) ───────────────────────────────────────────

@app.get("/api/health")
async def api_health():
    """Real subsystem health check — probes Fabric, IPFS, Gateway, Detection, GOP Anchor."""
    try:
        result: Dict[str, Any] = {}

        # 1. Fabric
        try:
            bn = await asyncio.to_thread(get_latest_block_number, fabric_env, CHANNEL_NAME)
            anchor_successes = int(connection_status.get("anchor_successes", 0) or 0)
            anchor_failures = int(connection_status.get("anchor_failures", 0) or 0)

            if anchor_failures > 0 and anchor_successes == 0:
                writer_status = "degraded"
                writer_hint = "读链正常，但近期写链未成功"
            elif anchor_failures > anchor_successes:
                writer_status = "degraded"
                writer_hint = "写链成功率偏低，建议检查 Fabric 提交链路"
            elif anchor_successes > 0:
                writer_status = "ok"
                writer_hint = "读写链路可用"
            else:
                writer_status = "unknown"
                writer_hint = "暂无近期写链结果"

            result["fabric"] = {
                "status": "ok",
                "block_height": bn,
                "writer_status": writer_status,
                "writer_hint": writer_hint,
            }
            connection_status["fabric_last_success"] = time.time()
        except Exception as e:
            result["fabric"] = {"status": "error", "message": str(e)}

        # 2. IPFS
        try:
            storage = VideoStorage()
            stats = storage.get_node_stats()
            result["ipfs"] = {"status": "ok", **stats}
            connection_status["ipfs_last_success"] = time.time()
        except Exception as e:
            result["ipfs"] = {"status": "error", "message": str(e)}

        # 3. Gateway
        try:
            epochs = await asyncio.to_thread(gateway_service.list_epochs, 1)
            result["gateway"] = {
                "status": "ok",
                "latest_epoch": epochs[0]["epoch_id"] if epochs else "暂无",
            }
        except Exception as e:
            result["gateway"] = {"status": "error", "message": str(e)}

        # 4. YOLO Detection
        result["detection"] = {
            "status": "running" if detection_thread.is_alive() else "stopped",
            "model": selected_model,
            "device": DEVICE,
        }

        # 5. GOP Anchor
        splitter_thread = getattr(getattr(gop_anchor, "_splitter", None), "_ingest_thread", None)
        anchor_stats = gop_anchor.get_runtime_stats() if gop_anchor else {}
        connection_status["stream_reconnects"] = int(anchor_stats.get("reconnect_count", 0) or 0)
        result["gop_anchor"] = {
            "status": "running" if splitter_thread and splitter_thread.is_alive() else "stopped",
            **anchor_stats,
        }
        if ring_buffer_manager:
            result["local_buffer"] = ring_buffer_manager.get_stats()

        # 6. Connection tracking
        result["connections"] = dict(connection_status)

        return result
    except Exception as e:
        logger.exception("[HEALTH] Unexpected failure")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ── Stream & WebSocket Routes ────────────────────────────────────

@app.get("/video_feed/{stream_type}")
def video_feed(stream_type: str):
    def generate():
        last_frame_data = None
        while True:
            with lock:
                frame_data = frame_buffer.get("ann" if stream_type == "ann" else "raw")
            if frame_data and frame_data is not last_frame_data:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame_data + b"\r\n"
                last_frame_data = frame_data
            time.sleep(0.03)
    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ── Evidence Verify (Merkle proof) ───────────────────────────────

@app.post("/api/verify/{event_id}")
def verify_evidence(event_id: str):
    json_path = EVIDENCE_DIR / f"{event_id}.json"
    event_data, merkle_info = None, None
    if json_path.exists():
        event_data = json.loads(json_path.read_text(encoding="utf-8"))
        merkle_info = event_data.get("_merkle")
    if not merkle_info:
        batches_dir = EVIDENCE_DIR / "batches"
        if batches_dir.exists():
            for bf in batches_dir.rglob("batch_*.json"):
                try:
                    bd = json.loads(bf.read_text(encoding="utf-8"))
                    for ev in bd.get("events", []):
                        if ev.get("event_id") == event_id:
                            merkle_info = {"proof": ev.get("proof", []), "merkleRoot": bd.get("merkle_root", ""),
                                           "batchId": bd.get("batch_id", ""), "txId": bd.get("tx_id", ""),
                                           "blockNumber": bd.get("block_number"), "timestamp": bd.get("timestamp")}
                            if not event_data: event_data = {"evidence_hash": ev.get("evidence_hash", "")}
                            break
                except Exception: continue
                if merkle_info: break
    if not merkle_info:
        return JSONResponse({"status": "error", "message": "未上链/不存在"}, status_code=404)
    evidence_hash = event_data.get("evidence_hash", "")
    proof = merkle_info.get("proof", [])
    expected_root = merkle_info.get("merkleRoot", "")
    computed_root = apply_merkle_proof(evidence_hash, proof)
    verified = computed_root == expected_root
    return JSONResponse({"status": "success" if verified else "failed", "verified": verified, "match": verified,
                         "local_hash": evidence_hash, "proof_root": computed_root, "expected_root": expected_root,
                         "batch_id": merkle_info.get("batchId", ""), "tx_id": merkle_info.get("txId", ""),
                         "block_number": merkle_info.get("blockNumber"), "onchain_time": merkle_info.get("timestamp")})

@app.get("/api/history/{event_id}")
def get_event_history(event_id: str):
    try:
        result = query_chaincode(fabric_env, CHANNEL_NAME, CHAINCODE_NAME, "GetEvidenceHistory", [event_id])
        return JSONResponse({"history": json.loads(result) if result else []})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Blockchain Ledger ────────────────────────────────────────────

@app.get("/api/ledger/recent")
def api_get_recent_blocks(limit: int = 20):
    try:
        blocks = []
        for batch in _load_batch_details():
            bn = batch.get("block_number")
            if bn is None:
                continue
            blocks.append({
                "batch_id": batch.get("batch_id", ""),
                "block_number": bn,
                "tx_id": batch.get("tx_id", ""),
                "merkle_root": batch.get("merkle_root", ""),
                "event_count": batch.get("event_count", len(batch.get("events", []))),
                "timestamp": batch.get("timestamp", 0),
                "device_id": batch.get("device_id") or batch.get("camera_id", ""),
            })
        blocks.sort(key=lambda b: b["block_number"], reverse=True)
        safe_limit = max(1, min(int(limit or 20), 60))
        return JSONResponse(
            {"blocks": blocks[:safe_limit]},
            headers={"Cache-Control": "no-store"},
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/batch/{batch_id}")
def api_get_batch_details(batch_id: str):
    try:
        bd = next((batch for batch in _load_batch_details() if batch.get("batch_id") == batch_id), None)
        if not bd:
            return JSONResponse({"error": "Batch not found"}, status_code=404)
        return JSONResponse({"status": "success", "batch_id": bd.get("batch_id"), "block_number": bd.get("block_number"),
                             "tx_id": bd.get("tx_id"), "merkle_root": bd.get("merkle_root"), "timestamp": bd.get("timestamp"),
                             "event_count": bd.get("event_count"), "events": bd.get("events", []),
                             "device_id": bd.get("device_id") or bd.get("camera_id", ""),
                             "window_start": bd.get("window_start"), "window_end": bd.get("window_end")})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/ledger/query")
def api_query_ledger(q: str = ""):
    try:
        query = (q or "").strip()
        if not query:
            return JSONResponse({"error": "query is required"}, status_code=400)

        batch_details = _load_batch_details()
        if not batch_details:
            return JSONResponse({"error": "Batch not found"}, status_code=404)

        query_lower = query.lower()
        matched = None
        is_block_number_query = query.isdigit()

        for batch in sorted(batch_details, key=lambda item: item.get("block_number", 0), reverse=True):
            block_number = batch.get("block_number")
            batch_id = str(batch.get("batch_id", "") or "")
            tx_id = str(batch.get("tx_id", "") or "")

            if str(block_number) == query:
                matched = batch
                break
            if is_block_number_query:
                continue
            if batch_id.lower() == query_lower or query_lower in batch_id.lower():
                matched = batch
                break
            if tx_id.lower() == query_lower or query_lower in tx_id.lower():
                matched = batch
                break

        if not matched:
            return JSONResponse({"error": "Batch not found"}, status_code=404)

        return JSONResponse({
            "status": "success",
            "batch_id": matched.get("batch_id"),
            "block_number": matched.get("block_number"),
            "tx_id": matched.get("tx_id"),
            "merkle_root": matched.get("merkle_root"),
            "timestamp": matched.get("timestamp"),
            "event_count": matched.get("event_count", len(matched.get("events", []))),
            "events": matched.get("events", []),
            "device_id": matched.get("device_id") or matched.get("camera_id", ""),
            "window_start": matched.get("window_start"),
            "window_end": matched.get("window_end"),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/config")
def api_get_config():
    return JSONResponse(get_fabric_config())


# ── Video Evidence API ───────────────────────────────────────────

@app.post("/api/video/upload")
async def api_video_upload(file: UploadFile = File(...), device_id: str = "cctv-default-01"):
    """Upload video → GOP split → IPFS upload → Fabric anchor → SQLite index."""
    try:
        video_id = f"vid-{uuid.uuid4().hex[:12]}"
        suffix = Path(file.filename or "video.mp4").suffix
        save_path = UPLOAD_DIR / f"{video_id}{suffix}"
        with open(save_path, "wb") as f: shutil.copyfileobj(file.file, f)
        file_size = save_path.stat().st_size

        # 1. GOP split
        from services.gop_splitter import split_gops
        gops = await asyncio.to_thread(split_gops, str(save_path))
        if not gops:
            return JSONResponse({"error": "GOP 切分失败"}, status_code=400)

        # 2. IPFS upload (security policy: reject if IPFS unavailable)
        try:
            ipfs_storage = VideoStorage()
            for g in gops:
                await asyncio.to_thread(ipfs_storage.upload_gop, device_id, g)
            connection_status["ipfs_last_success"] = time.time()
            logger.info(f"[UPLOAD] {len(gops)} GOPs uploaded to IPFS for {video_id}")
        except Exception as e:
            logger.error(f"[UPLOAD] IPFS unavailable, rejecting upload: {e}")
            return JSONResponse(
                {"error": f"IPFS 存储不可用，上传被拒绝（安全策略）: {e}"},
                status_code=503,
            )

        # 3. Merkle tree + signature
        from services.merkle_utils import build_merkle_root_and_proofs
        from services.crypto_utils import build_batch_signature_material
        merkle_root, proofs = build_merkle_root_and_proofs(gops)
        batch_id = f"batch-{video_id}"
        event_ids = [f"{video_id}-gop{g.gop_id}" for g in gops]
        event_hashes = [g.sha256_hash for g in gops]
        event_vifs = [g.vif or "" for g in gops]
        window_start = int(min(g.start_time for g in gops))
        window_end = int(max(g.end_time for g in gops))
        cert_pem, sig_b64, ph = build_batch_signature_material(
            batch_id, device_id, merkle_root, window_start, window_end,
            event_ids, event_hashes, Path(SETTINGS.device_cert_path), Path(SETTINGS.device_key_path),
            SETTINGS.device_sign_algo, SETTINGS.device_signature_required,
            event_vifs=event_vifs)

        # 4. Fabric anchor (with retry)
        result = await asyncio.to_thread(
            invoke_with_retry, "CreateEvidenceBatch",
            [batch_id, device_id, merkle_root, str(window_start), str(window_end), json.dumps(event_ids),
             json.dumps(event_hashes), json.dumps(event_vifs), cert_pem, sig_b64, ph],
        )
        tx_id = result.get("tx_id", "")
        block_number = await asyncio.to_thread(get_latest_block_number, fabric_env, CHANNEL_NAME)

        # 5. SQLite index
        insert_video(video_id=video_id, device_id=device_id, filename=file.filename or "unknown",
                     file_size=file_size, gop_count=len(gops), merkle_root=merkle_root, tx_id=tx_id, block_number=block_number)
        insert_video_gops(video_id, [{"video_id": video_id, "gop_index": g.gop_id, "sha256": g.sha256_hash,
            "vif": g.vif, "start_time": g.start_time, "end_time": g.end_time,
            "frame_count": g.frame_count, "byte_size": g.byte_size} for g in gops])

        logger.info(f"[UPLOAD] {video_id}: {len(gops)} GOPs, merkle={merkle_root[:16]}... tx={tx_id[:16]}...")
        return JSONResponse({"status": "success", "video_id": video_id, "filename": file.filename,
                             "gop_count": len(gops), "merkle_root": merkle_root, "tx_id": tx_id, "block_number": block_number})
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/video/list")
def api_video_list():
    return JSONResponse({"videos": list_videos()})

@app.get("/api/video/{video_id}/certificate")
def api_video_certificate(video_id: str):
    video = get_video(video_id)
    if not video: return JSONResponse({"error": "Video not found"}, status_code=404)

    # Enrich GOPs with IPFS CID from IPFSIndex
    gops = get_video_gops(video_id)
    try:
        ipfs_storage = VideoStorage()
        playable_ranges = []
        for gop in gops:
            record = ipfs_storage.get_gop_record(
                video.get("device_id", ""),
                sha256_hash=gop.get("sha256", ""),
            )
            _enrich_gop_playback_urls(video.get("device_id", ""), gop, record, ipfs_storage)
            if record and ipfs_storage.has_playback_metadata(record):
                if gop.get("start_time") is not None and gop.get("end_time") is not None:
                    playable_ranges.append((gop["start_time"], gop["end_time"]))
        if playable_ranges:
            start_time = min(r[0] for r in playable_ranges)
            end_time = max(r[1] for r in playable_ranges)
            video["playback_playlist_url"] = _relative_gop_playlist_url(
                video.get("device_id", ""),
                start_time,
                end_time,
            )
    except Exception:
        pass  # IPFS offline is non-fatal for read operations

    return JSONResponse({"status": "success", **video, "gops": gops})


# ── Video Verification (Phase 2: auto-trigger + WS alert) ───────

@app.post("/api/video/verify")
async def api_video_verify(file: UploadFile = File(...), original_video_id: str = ""):
    """Verify uploaded video against original — tri-state per-GOP comparison."""
    try:
        if not original_video_id: return JSONResponse({"error": "必须指定 original_video_id"}, status_code=400)
        original = get_video(original_video_id)
        if not original: return JSONResponse({"error": "原始视频不存在"}, status_code=404)
        original_gops = get_video_gops(original_video_id)
        if not original_gops: return JSONResponse({"error": "原始 GOP 记录不存在"}, status_code=404)
        suffix = Path(file.filename or "video.mp4").suffix
        tmp = UPLOAD_DIR / f"verify-{uuid.uuid4().hex[:8]}{suffix}"
        with open(tmp, "wb") as f: shutil.copyfileobj(file.file, f)
        from services.gop_splitter import split_gops
        curr_gops = await asyncio.to_thread(split_gops, str(tmp))
        gop_results, worst, max_risk = _compare_gop_sequences(original_gops, curr_gops)
        rec, wo_result = await _finalize_verify_outcome(
            original_video_id,
            file.filename or "unknown",
            worst,
            max_risk,
            gop_results,
            workorder_subject=f"视频 {original_video_id} 完整性验证异常",
            broadcast_video_id=original_video_id,
        )

        try: tmp.unlink(missing_ok=True)
        except Exception: pass
        return JSONResponse({"status": "success", "verify_id": rec["id"], "overall_status": worst,
                             "overall_risk": round(max_risk, 4), "original_gop_count": len(original_gops),
                             "current_gop_count": len(curr_gops), "gop_results": gop_results,
                             "workorder": wo_result})
    except Exception as e:
        import traceback; traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/video/verify/export")
async def api_video_verify_export(file: UploadFile = File(...)):
    """Verify a SecureLens-exported TS sample against its referenced IPFS GOPs."""
    tmp: Optional[Path] = None
    try:
        parsed = _parse_export_sample_filename(file.filename or "")
        storage = VideoStorage()
        reference_gops = _build_reference_gops_for_export(
            storage,
            parsed["device_id"],
            parsed["actual_start_time"],
            parsed["actual_end_time"],
        )
        if not reference_gops:
            return JSONResponse({"error": "导出样本对应的原始 GOP 记录不存在"}, status_code=404)

        suffix = Path(file.filename or "sample.ts").suffix or ".ts"
        tmp = UPLOAD_DIR / f"verify-export-{uuid.uuid4().hex[:8]}{suffix}"
        with open(tmp, "wb") as f:
            shutil.copyfileobj(file.file, f)

        from services.gop_splitter import split_gops
        curr_gops = await asyncio.to_thread(split_gops, str(tmp))
        aligned_reference_gops, gop_results, worst, max_risk = _align_reference_gops_for_export_verify(
            reference_gops,
            curr_gops,
            expected_gop_count=parsed["expected_gop_count"],
        )

        original_video_id = (
            f"export:{parsed['device_id']}:{int(parsed['actual_start_time'])}-{int(parsed['actual_end_time'])}"
        )
        rec, wo_result = await _finalize_verify_outcome(
            original_video_id,
            file.filename or "unknown",
            worst,
            max_risk,
            gop_results,
            verify_mode="export_sample",
            reference_device_id=parsed["device_id"],
            reference_start_time=parsed["actual_start_time"],
            reference_end_time=parsed["actual_end_time"],
            gap_flag=parsed["gap_flag"],
            matched_gop_count=len(aligned_reference_gops),
            workorder_subject=(
                f"导出样本 {parsed['device_id']} "
                f"[{_format_replay_label(parsed['actual_start_time'])} - {_format_replay_label(parsed['actual_end_time'])}] "
                "完整性验证异常"
            ),
            broadcast_video_id=parsed["device_id"],
        )

        return JSONResponse({
            "status": "success",
            "verify_id": rec["id"],
            "verify_mode": "export_sample",
            "overall_status": worst,
            "overall_risk": round(max_risk, 4),
            "reference_device_id": parsed["device_id"],
            "reference_start_time": parsed["actual_start_time"],
            "reference_end_time": parsed["actual_end_time"],
            "gap_flag": parsed["gap_flag"],
            "expected_gop_count": parsed["expected_gop_count"],
            "matched_gop_count": len(aligned_reference_gops),
            "current_gop_count": len(curr_gops),
            "gop_results": gop_results,
            "workorder": wo_result,
        })
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        logger.error(f"[VERIFY_EXPORT] Failed: {e}")
        import traceback; traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/video/tamper/export")
async def api_video_tamper_export(file: UploadFile = File(...)):
    """Generate a tampered version of a SecureLens-exported TS sample."""
    tmp_original: Optional[Path] = None
    try:
        _cleanup_tamper_jobs()
        parsed = _parse_export_sample_filename(file.filename or "")
        storage = VideoStorage()
        reference_gops = _build_reference_gops_for_export(
            storage,
            parsed["device_id"],
            parsed["actual_start_time"],
            parsed["actual_end_time"],
        )
        if not reference_gops:
            return JSONResponse({"error": "导出样本对应的原始 GOP 记录不存在"}, status_code=404)

        suffix = Path(file.filename or "sample.ts").suffix or ".ts"
        job_id = f"tamper-{uuid.uuid4().hex[:12]}"
        job_dir = TAMPER_JOB_DIR / job_id
        original_dir = job_dir / "original"
        tampered_dir = job_dir / "tampered"
        original_dir.mkdir(parents=True, exist_ok=True)
        tampered_dir.mkdir(parents=True, exist_ok=True)

        original_name = Path(file.filename or f"sample{suffix}").name
        tmp_original = original_dir / original_name
        with tmp_original.open("wb") as f:
            shutil.copyfileobj(file.file, f)

        from services.gop_splitter import split_gops

        attempts: List[Dict[str, Any]] = []
        tampered_path = tampered_dir / TAMPER_JOB_SEGMENT_NAME
        final_gop_results: List[Dict[str, Any]] = []
        final_worst = "RE_ENCODED"
        final_risk = 0.0
        final_meta: Optional[Dict[str, Any]] = None
        target_gop_seconds = None
        if len(reference_gops) >= 2:
            durations = [
                max(float((g.get("end_time") or 0.0) - (g.get("start_time") or 0.0)), 0.0)
                for g in reference_gops
            ]
            positive_durations = [value for value in durations if value > 0]
            if positive_durations:
                target_gop_seconds = sum(positive_durations) / len(positive_durations)

        for replace_seconds in TAMPER_DURATIONS_SECONDS:
            attempt_output = tampered_dir / f"attempt_{str(replace_seconds).replace('.', '_')}.ts"
            try:
                windows = await asyncio.to_thread(
                    _run_frame_replace_tamper,
                    tmp_original,
                    attempt_output,
                    replace_seconds,
                    target_gop_seconds=target_gop_seconds,
                )
                curr_gops = await asyncio.to_thread(split_gops, str(attempt_output))
                gop_results, worst, max_risk = _compare_gop_sequences(reference_gops, curr_gops)
                attempt = {
                    "replace_seconds": replace_seconds,
                    "status": worst,
                    "risk": round(max_risk, 4),
                    "tamper_window": windows,
                    "current_gop_count": len(curr_gops),
                }
                attempts.append(attempt)
                final_gop_results = gop_results
                final_worst = worst
                final_risk = max_risk
                if worst == "TAMPERED":
                    attempt_output.replace(tampered_path)
                    preview_duration = _probe_video_duration(tampered_path)
                    final_meta = {
                        "mode": "frame_replace",
                        "replace_seconds": windows["replace_seconds"],
                        "tamper_start": windows["tamper_start"],
                        "tamper_end": windows["tamper_end"],
                        "source_start": windows["source_start"],
                        "source_end": windows["source_end"],
                        "preview_duration_seconds": round(preview_duration, 6),
                    }
                    break
            except Exception as attempt_error:
                attempts.append({
                    "replace_seconds": replace_seconds,
                    "status": "ERROR",
                    "error": str(attempt_error),
                })
                continue

        if not final_meta or not tampered_path.exists():
            return JSONResponse(
                {
                    "error": "当前样本无法稳定生成可检出的篡改版本，请更换更长的导出 TS 样本后重试。",
                    "attempts": attempts,
                    "overall_status": final_worst,
                    "overall_risk": round(final_risk, 4),
                    "gop_results": final_gop_results,
                },
                status_code=422,
            )

        job_meta = {
            "job_id": job_id,
            "created_at": time.time(),
            "source_filename": original_name,
            "download_filename": original_name,
            "reference": {
                "device_id": parsed["device_id"],
                "actual_start_time": parsed["actual_start_time"],
                "actual_end_time": parsed["actual_end_time"],
                "expected_gop_count": parsed["expected_gop_count"],
                "gap_flag": parsed["gap_flag"],
                "matched_gop_count": len(reference_gops),
            },
            "overall_status": final_worst,
            "overall_risk": round(final_risk, 4),
            "tamper_meta": final_meta,
            "attempts": attempts,
        }
        _write_tamper_job_meta(job_dir, job_meta)

        return JSONResponse({
            "status": "success",
            "job_id": job_id,
            "download_filename": original_name,
            "download_url": f"/api/video/tamper/jobs/{job_id}/download",
            "preview_playlist_url": f"/api/video/tamper/jobs/{job_id}/preview.m3u8",
            "overall_status": final_worst,
            "overall_risk": round(final_risk, 4),
            "tamper_meta": {
                **final_meta,
                "gap_flag": parsed["gap_flag"],
                "reference_device_id": parsed["device_id"],
                "reference_start_time": parsed["actual_start_time"],
                "reference_end_time": parsed["actual_end_time"],
            },
            "attempts": attempts,
        })
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        logger.error(f"[TAMPER_EXPORT] Failed: {e}")
        import traceback; traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/video/tamper/jobs/{job_id}/preview.m3u8")
async def api_video_tamper_preview_playlist(job_id: str):
    try:
        _, meta = _load_tamper_job_meta(job_id)
        duration_seconds = float(meta.get("tamper_meta", {}).get("preview_duration_seconds") or 0.0)
        if duration_seconds <= 0:
            raise FileNotFoundError("Tamper preview not found")
        return _build_tamper_playlist_response(job_id, duration_seconds)
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        logger.error(f"[TAMPER_PREVIEW] Failed to build preview playlist: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/video/tamper/jobs/{job_id}/segment.ts")
async def api_video_tamper_segment(job_id: str):
    try:
        job_dir, _ = _load_tamper_job_meta(job_id)
        segment_path = job_dir / "tampered" / TAMPER_JOB_SEGMENT_NAME
        if not segment_path.exists():
            raise FileNotFoundError("Tamper preview segment not found")
        return Response(
            content=segment_path.read_bytes(),
            media_type="video/mp2t",
            headers={"Cache-Control": "no-store"},
        )
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        logger.error(f"[TAMPER_SEGMENT] Failed to stream tamper segment: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/video/tamper/jobs/{job_id}/download")
async def api_video_tamper_download(job_id: str):
    try:
        job_dir, meta = _load_tamper_job_meta(job_id)
        segment_path = job_dir / "tampered" / TAMPER_JOB_SEGMENT_NAME
        if not segment_path.exists():
            raise FileNotFoundError("Tampered sample not found")
        filename = meta.get("download_filename") or "sample.ts"
        encoded = base64.b64encode(filename.encode("utf-8")).decode("ascii")
        return FileResponse(
            path=segment_path,
            media_type="video/mp2t",
            filename=filename,
            headers={
                "Cache-Control": "no-store",
                "X-Download-Filename-B64": encoded,
            },
        )
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        logger.error(f"[TAMPER_DOWNLOAD] Failed to export tampered sample: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/video/verify/history")
def api_verify_history(limit: int = 50):
    return JSONResponse({"history": list_verify_history(limit)})


# ── Verification Stats (Phase 2.3) ──────────────────────────────

@app.get("/api/stats/verification")
def api_verify_stats():
    """Verification statistics: total, status breakdown, integrity rate."""
    history = list_verify_history(1000)
    total = len(history)
    counts = {"INTACT": 0, "RE_ENCODED": 0, "TAMPERED": 0}
    for h in history:
        s = h.get("overall_status", "TAMPERED")
        counts[s] = counts.get(s, 0) + 1
    return {
        "total_verifications": total,
        "status_counts": counts,
        "integrity_rate": round(counts["INTACT"] / max(total, 1), 4),
    }


# ── GOP Verifier API (Phase 1.3) ────────────────────────────────

@app.post("/api/gop/verify")
async def api_gop_verify(request: Request):
    """End-to-end GOP verification: IPFS download → SHA-256 recompute → Fabric on-chain verify."""
    d = await request.json()
    device_id = d.get("device_id", CAMERA_ID)
    epoch_id = d.get("epoch_id", "")
    gop_index = int(d.get("gop_index", 0))

    try:
        storage = VideoStorage()
        verifier = GOPVerifier(
            storage=storage,
            fabric_env=fabric_env,
            orderer_ca=ORDERER_CA,
            org2_tls=ORG2_TLS,
            channel=CHANNEL_NAME,
            chaincode=CHAINCODE_NAME,
        )
        result = await asyncio.to_thread(verifier.verify_gop, device_id, epoch_id, gop_index)
        return JSONResponse(result)
    except FileNotFoundError as e:
        return JSONResponse({"status": "NOT_INTACT", "reason": str(e)}, status_code=404)
    except ValueError as e:
        return JSONResponse({"status": "error", "reason": str(e)}, status_code=400)
    except Exception as e:
        logger.error(f"[GOP_VERIFY] Failed: {e}")
        return JSONResponse({"status": "error", "reason": str(e)}, status_code=500)


# ── Device List API (Phase 1.5) ──────────────────────────────────

@app.get("/api/devices")
async def api_list_devices():
    """Real device list from Gateway DB + current GOP anchor status."""
    devices = []
    seen = set()

    # From gateway_service: devices that have reported
    try:
        epochs = await asyncio.to_thread(gateway_service.list_epochs, 5)
        for ep in epochs:
            try:
                detail = await asyncio.to_thread(gateway_service.get_epoch, ep["epoch_id"])
                if detail:
                    for d in detail.get("devices", []):
                        if d["device_id"] not in seen:
                            seen.add(d["device_id"])
                            devices.append({
                                "device_id": d["device_id"],
                                "status": "online",
                                "segment_root": d.get("segment_root", ""),
                                "gop_count": d.get("gop_count", 0),
                            })
            except Exception:
                pass
    except Exception:
        pass

    # Locally configured camera streams. Only the primary stream runs detection/anchoring.
    for camera in SETTINGS.camera_configs:
        device_id = camera.get("device_id", "").strip()
        stream_url = camera.get("video_source", "").strip()
        if not device_id or device_id in seen:
            continue

        is_primary = device_id == CAMERA_ID
        devices.append({
            "device_id": device_id,
            "status": "detecting" if is_primary and detection_thread.is_alive() else "online",
            "video_source": stream_url,
            "label": camera.get("label", device_id),
            "pending_gops": len(gop_anchor._pending_gops) if is_primary and gop_anchor else 0,
        })
        seen.add(device_id)

    devices.sort(key=lambda device: (device.get("device_id") != CAMERA_ID, device.get("label") or device.get("device_id") or ""))
    return {"devices": devices}


# ── IPFS API (Phase 1.2 — browse) ───────────────────────────────

def _replace_url_port(url: str, port: int) -> str:
    parsed = urlparse(url)
    hostname = parsed.hostname or "localhost"
    netloc = f"{hostname}:{port}"
    if parsed.username:
        auth = parsed.username
        if parsed.password:
            auth = f"{auth}:{parsed.password}"
        netloc = f"{auth}@{netloc}"
    return urlunparse((parsed.scheme or "http", netloc, parsed.path or "", parsed.params, parsed.query, parsed.fragment))


def _build_ipfs_cluster_targets() -> List[Dict[str, str]]:
    api_base = SETTINGS.ipfs_api_url or "http://localhost:5001"
    gateway_base = SETTINGS.ipfs_gateway_url or "http://localhost:8080"
    return [
        {
            "name": "node0",
            "label": "节点 1",
            "api_url": _replace_url_port(api_base, 5001),
            "gateway_url": _replace_url_port(gateway_base, 8080),
        },
        {
            "name": "node1",
            "label": "节点 2",
            "api_url": _replace_url_port(api_base, 5002),
            "gateway_url": _replace_url_port(gateway_base, 8081),
        },
        {
            "name": "node2",
            "label": "节点 3",
            "api_url": _replace_url_port(api_base, 5003),
            "gateway_url": _replace_url_port(gateway_base, 8082),
        },
    ]

@app.get("/api/ipfs/stats")
async def api_ipfs_stats():
    """IPFS node statistics."""
    try:
        storage = VideoStorage()
        stats = storage.get_node_stats()
        node_info = storage.client.id()
        time_bounds = storage.get_gop_time_bounds()
        cluster_nodes = []
        for target in _build_ipfs_cluster_targets():
            try:
                client = IPFSClient(target["api_url"])
                target_id = client.id()
                target_stats = client.repo_stat()
                cluster_nodes.append({
                    **target,
                    "status": "ok",
                    "peer_id": target_id.get("ID", "unknown"),
                    "repo_size": target_stats.get("RepoSize", 0),
                    "num_objects": target_stats.get("NumObjects", 0),
                })
            except Exception as cluster_error:
                cluster_nodes.append({
                    **target,
                    "status": "error",
                    "peer_id": "",
                    "repo_size": 0,
                    "num_objects": 0,
                    "message": str(cluster_error),
                })
        latest_by_device = {
            item["device_id"]: {
                "earliest_timestamp": item.get("earliest_timestamp"),
                "latest_timestamp": item.get("latest_timestamp"),
                "gop_count": item.get("gop_count", 0),
            }
            for item in time_bounds
        }
        latest_overall = time_bounds[0] if time_bounds else None
        return {
            "status": "ok",
            **stats,
            "peer_id": node_info.get("ID", "unknown"),
            "gateway_url": storage.gateway_url,
            "cluster_nodes": cluster_nodes,
            "cluster_online_count": sum(1 for node in cluster_nodes if node.get("status") == "ok"),
            "cluster_total_count": len(cluster_nodes),
            "latest_gop_by_device": latest_by_device,
            "latest_gop_timestamp": latest_overall.get("latest_timestamp") if latest_overall else None,
            "latest_gop_device_id": latest_overall.get("device_id") if latest_overall else None,
        }
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=503)

@app.get("/api/ipfs/gops")
async def api_ipfs_list_gops(device_id: str = "", start: float = 0, end: float = 0):
    """List GOPs stored in IPFS for a device in a time range."""
    try:
        storage = VideoStorage()
        if not device_id:
            device_id = CAMERA_ID
        if end == 0:
            end = time.time()
        if start == 0:
            start = end - 86400  # default: last 24h
        gops = storage.list_gops(device_id, start, end)
        # Enrich with gateway URLs
        for g in gops:
            g["gateway_url"] = storage.get_gateway_url(g["ipfs_cid"])
            g["duration"] = g.get("duration_seconds")
            if storage.has_playback_metadata(g):
                g["playback_segment_url"] = _relative_gop_segment_url(device_id, g["ipfs_cid"])
                g["playback_playlist_url"] = _relative_gop_playlist_url(
                    device_id,
                    g["timestamp"],
                    g["timestamp"] + max(g.get("duration_seconds") or 0.0, 0.001),
                )
            for internal_key in (
                "codec_name", "codec_extradata_b64", "width", "height", "pix_fmt",
                "time_base_num", "time_base_den", "frame_rate_num", "frame_rate_den",
                "packet_sizes_json", "packet_pts_json", "packet_dts_json", "packet_keyframes_json",
                "packet_sizes", "packet_pts", "packet_dts", "packet_keyframes",
                "duration_seconds", "created_at", "content_type", "id",
            ):
                g.pop(internal_key, None)
        return {"gops": gops, "count": len(gops)}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/ipfs/segment/{cid}.ts")
async def api_ipfs_gop_segment(cid: str, device_id: str = ""):
    """Build a playable MPEG-TS segment on demand from a raw GOP."""
    try:
        storage = VideoStorage()
        if not device_id:
            device_id = CAMERA_ID
        ts_bytes = await asyncio.to_thread(storage.build_ts_segment, device_id, cid)
        return Response(
            content=ts_bytes,
            media_type="video/mp2t",
            headers={"Cache-Control": "no-store"},
        )
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=422)
    except Exception as e:
        logger.error(f"[IPFS_SEGMENT] Failed to build TS segment for {cid}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/ipfs/playlist.m3u8")
async def api_ipfs_playlist(device_id: str = "", start: float = 0, end: float = 0):
    """Generate an HLS playlist from stored raw GOPs by time range."""
    try:
        storage = VideoStorage()
        if not device_id:
            device_id = CAMERA_ID
        if end == 0:
            end = time.time()
        if start == 0:
            start = end - 30
        return _build_playlist_response(storage, device_id, start, end)
    except Exception as e:
        logger.error(f"[IPFS_PLAYLIST] Failed to build playlist: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/ipfs/replay/playlist.m3u8")
async def api_ipfs_replay_playlist(
    device_id: str = "",
    start_local: str = "",
    end_local: str = "",
    timezone: str = DEFAULT_REPLAY_TIMEZONE,
):
    """Generate an HLS playlist from East-8 wall clock inputs."""
    try:
        storage = VideoStorage()
        if not device_id:
            device_id = CAMERA_ID
        start_ts, end_ts, _ = _resolve_replay_range(start_local, end_local, timezone)
        return _build_playlist_response(storage, device_id, start_ts, end_ts)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except Exception as e:
        logger.error(f"[IPFS_REPLAY] Failed to build replay playlist: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/ipfs/replay/download.ts")
async def api_ipfs_replay_download_ts(
    device_id: str = "",
    start_local: str = "",
    end_local: str = "",
    timezone: str = DEFAULT_REPLAY_TIMEZONE,
):
    """Export matched replay GOPs as a single MPEG-TS attachment."""
    try:
        storage = VideoStorage()
        if not device_id:
            device_id = CAMERA_ID
        start_ts, end_ts, tz_name = _resolve_replay_range(start_local, end_local, timezone)
        payload = _build_replay_export_payload(
            storage,
            device_id,
            start_ts,
            end_ts,
            timezone_name=tz_name,
            requested_start_local=start_local,
            requested_end_local=end_local,
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        logger.error(f"[IPFS_REPLAY_DOWNLOAD_TS] Failed to prepare replay TS export: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

    try:
        ts_bytes = await asyncio.to_thread(
            storage.build_ts_stream,
            device_id,
            [g["ipfs_cid"] for g in payload["playable_gops"]],
        )
        filename = f"{payload['filename_base']}.ts"
        return Response(
            content=ts_bytes,
            media_type="video/mp2t",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=422)
    except Exception as e:
        logger.error(f"[IPFS_REPLAY_DOWNLOAD_TS] Failed to export replay TS: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/ipfs/replay/download.json")
async def api_ipfs_replay_download_json(
    device_id: str = "",
    start_local: str = "",
    end_local: str = "",
    timezone: str = DEFAULT_REPLAY_TIMEZONE,
):
    """Export replay manifest JSON alongside the TS sample."""
    try:
        storage = VideoStorage()
        if not device_id:
            device_id = CAMERA_ID
        start_ts, end_ts, tz_name = _resolve_replay_range(start_local, end_local, timezone)
        payload = _build_replay_export_payload(
            storage,
            device_id,
            start_ts,
            end_ts,
            timezone_name=tz_name,
            requested_start_local=start_local,
            requested_end_local=end_local,
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        logger.error(f"[IPFS_REPLAY_DOWNLOAD_JSON] Failed to prepare replay manifest: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

    try:
        filename = f"{payload['filename_base']}.json"
        return Response(
            content=json.dumps(payload["manifest"], ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=422)
    except Exception as e:
        logger.error(f"[IPFS_REPLAY_DOWNLOAD_JSON] Failed to export replay manifest: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


# ── EIS/MAB Anchor Stats API (Phase 4) ──────────────────────────

@app.get("/api/anchor/stats")
def api_anchor_stats():
    """EIS + MAB real-time status."""
    result: Dict[str, Any] = {"mode": ANCHOR_STRATEGY}

    # EIS
    if eis_engine:
        result["eis"] = {
            "current_level": eis_engine._current_level,
            "current_eis": getattr(eis_engine, "_latest_eis", 0.0),
            "eis_mode": eis_engine.eis_mode,
            "confirm_counter": eis_engine._confirm_counter,
            "pending_level": eis_engine._pending_level,
            "eis_history": list(eis_engine._eis_history)[-10:],
            "thresholds": {
                "low": AdaptiveAnchor.LOW_THRESHOLD,
                "high": AdaptiveAnchor.HIGH_THRESHOLD,
            },
            "intervals": {
                "LOW": AdaptiveAnchor.INTERVAL_LOW,
                "MEDIUM": AdaptiveAnchor.INTERVAL_MEDIUM,
                "HIGH": AdaptiveAnchor.INTERVAL_HIGH,
            },
        }

    # MAB
    if mab_manager:
        result["mab"] = mab_manager.get_stats()

    # GOP Anchor
    if gop_anchor:
        result["anchor"] = {
            "pending_gops": len(gop_anchor._pending_gops),
            "segment_gops": gop_anchor.segment_gops,
        }

    return result


# ── Workorder API ────────────────────────────────────────────────

@app.post("/api/workorder/create")
async def api_create_workorder(request: Request):
    try:
        d = await request.json()
        return JSONResponse(create_workorder(d["violationId"], d["description"], d["assignedOrg"], int(d["deadline"])))
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/workorder/submit")
async def api_submit_rectification(request: Request):
    try:
        d = await request.json()
        return JSONResponse(submit_rectification(d["orderId"], d["proof"], d.get("attachments", [])))
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/workorder/confirm")
async def api_confirm_rectification(request: Request):
    try:
        d = await request.json()
        return JSONResponse(confirm_rectification(d["orderId"], d["approved"], d.get("comments", "")))
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/workorder/overdue")
def api_query_overdue(org: Optional[str] = None, page: int = 1, limit: int = 20):
    return JSONResponse(query_overdue_workorders(org, page, limit))

@app.get("/api/workorder/{order_id}")
def api_get_workorder(order_id: str):
    try: return JSONResponse(query_workorder_by_id(order_id))
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/api/audit/export/{batch_id}")
def api_export_audit(batch_id: str):
    try: return JSONResponse(export_audit_trail(batch_id))
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/audit/verify")
async def api_verify_audit_report(request: Request):
    try:
        d = await request.json()
        bid, eh, mpj, mr = d.get("batchId","").strip(), d.get("eventHash","").strip(), d.get("merkleProofJSON","").strip(), d.get("merkleRoot","").strip()
        if not all([bid, eh, mpj, mr]):
            return JSONResponse({"verified": False, "message": "缺少必要参数"}, status_code=400)
        r = query_chaincode(fabric_env, CHANNEL_NAME, CHAINCODE_NAME, "VerifyEvent", [bid, eh, mpj, mr])
        v = r.strip().lower() == "true"
        return JSONResponse({"verified": v, "batchId": bid, "message": "验证通过" if v else "验证失败"})
    except Exception as e: return JSONResponse({"verified": False, "message": str(e)}, status_code=500)


# ── Gateway Routes ───────────────────────────────────────────────

@app.post("/report")
async def receive_device_report(report: DeviceReport):
    await gateway_service.add_device_report(report.model_dump())
    return {"status": "received", "device_id": report.device_id}

@app.get("/epochs")
async def api_list_epochs(limit: int = 20):
    return {"epochs": await asyncio.to_thread(gateway_service.list_epochs, limit)}

@app.get("/epoch/{epoch_id}")
async def api_get_epoch(epoch_id: str):
    d = await asyncio.to_thread(gateway_service.get_epoch, epoch_id)
    if not d: raise HTTPException(404, "Epoch not found")
    return d

@app.get("/proof/{epoch_id}/{device_id}")
async def api_get_proof(epoch_id: str, device_id: str):
    p = await asyncio.to_thread(gateway_service.get_device_proof, epoch_id, device_id)
    if not p: raise HTTPException(404, "Proof not found")
    return p


# ══════════════════════════════════════════════════════════════════
# STARTUP
# ══════════════════════════════════════════════════════════════════

# ── Fabric environment ───────────────────────────────────────────
fabric_samples = Path(SETTINGS.fabric_samples_path).expanduser().resolve()
fabric_env, ORDERER_CA, ORG2_TLS = build_fabric_env(fabric_samples)

# ── Gateway service ──────────────────────────────────────────────
gateway_service = GatewayService(
    db_path="data/gateway.db",
    fabric_config={"env": fabric_env, "orderer_ca": ORDERER_CA, "org2_tls": ORG2_TLS,
                   "channel": CHANNEL_NAME, "chaincode": CHAINCODE_NAME},
)

# ── EIS adaptive anchor (Phase 4.1) ─────────────────────────────
EIS_MODE = os.getenv("EIS_MODE", "lite")
ANCHOR_STRATEGY = os.getenv("ANCHOR_STRATEGY", "fixed")  # fixed / mab_ucb / mab_thompson

eis_engine = AdaptiveAnchor(eis_mode=EIS_MODE, anchor_mode=ANCHOR_STRATEGY)
mab_manager = getattr(eis_engine, "_mab_manager", None)
if mab_manager:
    logger.info(f"MAB anchor manager initialized: strategy={ANCHOR_STRATEGY}")

logger.info(f"EIS engine initialized: mode={EIS_MODE}, anchor_strategy={ANCHOR_STRATEGY}")

# ── YOLO detection (feeds bridge + MJPEG) ────────────────────

def _yolo_frame_callback(boxes, class_names, frame):
    """每帧 YOLO 检测结果 → 桥接器 + 节流 WS 检测摘要"""
    yolo_bridge.feed(boxes, class_names, frame)

    now = time.time()
    if now - detection_ws_state["last_emit"] < 1.0:
        return

    detections = []
    if boxes is not None:
        for box in boxes[:12]:
            cls_id = int(box.cls[0])
            detections.append({
                "class_name": class_names.get(cls_id, f"class_{cls_id}"),
                "confidence": round(float(box.conf[0]), 3),
                "bbox": {
                    "x1": round(float(box.xyxy[0][0]), 1),
                    "y1": round(float(box.xyxy[0][1]), 1),
                    "x2": round(float(box.xyxy[0][2]), 1),
                    "y2": round(float(box.xyxy[0][3]), 1),
                },
            })

    try:
        loop = getattr(app.state, "main_loop", None)
        if loop and detections:
            detection_ws_state["last_emit"] = now
            asyncio.run_coroutine_threadsafe(
                ws_manager.broadcast({
                    "event_type": "detection_tick",
                    "timestamp": int(now),
                    "detections": detections,
                }),
                loop,
            )
    except Exception as e:
        logger.debug(f"[WS] detection summary skipped: {e}")

detection_thread = threading.Thread(
    target=start_detection_loop,
    args=(model, video_source, CONFIDENCE_THRESHOLD, ROAD_TARGET_CLASS_IDS, DEVICE,
          frame_buffer, lock, None,  # 旧事件级 Merkle 批处理已停用，当前仅保存事件证据文件
          {"min_frames": SETTINGS.aggregate_min_frames, "max_missed_frames": SETTINGS.aggregate_max_missed_frames,
           "iou_threshold": SETTINGS.aggregate_iou_threshold, "window_seconds": SETTINGS.aggregate_window_seconds}),
    kwargs={"on_frame_callback": _yolo_frame_callback},
    daemon=True,
)
detection_thread.start()

# ── GOP anchor — sole anchoring pipeline + EIS/MAB callbacks ────

def _eis_on_gop(gop):
    """每个 GOP 到达 → 从 YOLO 桥接器获取语义数据 → 喂 EIS 引擎"""
    try:
        semantic, keyframe = yolo_bridge.snapshot(gop.gop_id)
        decision = eis_engine.update(semantic, keyframe)
        
        # ★ 将 EIS/MAB 决策转换为新的 segment_gops 并注入
        if decision.mab_arm is not None:
            # MAB 模式：mab_arm 是臂索引 (0~3)，ARM_INTERVALS=[1,2,5,10]
            new_segment_gops = max(
                MIN_SEGMENT_GOPS,
                min(MAX_SEGMENT_GOPS, ARM_INTERVALS[decision.mab_arm]),
            )
        else:
            # Fixed/EIS 模式：用 interval_seconds ÷ GOP 平均时长
            new_segment_gops = max(
                MIN_SEGMENT_GOPS,
                min(MAX_SEGMENT_GOPS,
                    int(decision.report_interval_seconds / GOP_DURATION_SECONDS))
            )
        
        # 防抖：只有变化超过 20% 才真正更新（避免频繁抖动）
        old = gop_anchor.segment_gops
        if abs(new_segment_gops - old) / old > 0.2:
            gop_anchor.segment_gops = new_segment_gops
            logger.info(
                f"[EIS→ANCHOR] segment_gops 调整: {old} → {new_segment_gops} "
                f"(level={decision.level}, eis={decision.eis_score:.3f})"
            )
        else:
            logger.info(
                f"[EIS] GOP#{gop.gop_id} objects={semantic.total_count} "
                f"level={decision.level} eis={decision.eis_score:.3f} "
                f"should_report={decision.should_report_now}"
            )
    except Exception as e:
        logger.warning(f"[EIS] GOP#{gop.gop_id} update failed: {e}")

def _mab_on_anchor(segment_id, gops, result):
    """每次锚定完成 → 反馈 MAB 策略"""
    if eis_engine:
        eis_engine.report_anchor_result(
            success=result.get("success", False),
            cost=1.0,
            latency=0.0,
        )
    connection_status["anchor_successes" if result.get("success") else "anchor_failures"] += 1
    logger.info(f"[ANCHOR_CB] Segment {segment_id}: success={result.get('success')}, tx={result.get('tx_id', '')[:16]}")

gop_anchor = GOPAnchorManager(
    stream_url=anchor_video_source,
    device_id=CAMERA_ID,
    segment_gops=30,
    on_gop_callback=_eis_on_gop,
    on_anchor_callback=_mab_on_anchor,
    gop_build_queue_size=SETTINGS.gop_build_queue_size,
    ingest_mode=anchor_ingest_mode,
)

@app.on_event("startup")
async def startup_event():
    app.state.main_loop = asyncio.get_running_loop()
    scheduler = AsyncIOScheduler()
    scheduler.add_job(gateway_service.flush_epoch, 'interval', seconds=30)
    scheduler.start()
    app.state.scheduler = scheduler
    logger.info(
        "Purged previous runtime state before startup: "
        f"{STARTUP_PURGE_RESULT['videos']} live videos / "
        f"{STARTUP_PURGE_RESULT['video_gops']} video GOPs / "
        f"{STARTUP_PURGE_RESULT['verify_history']} verify records / "
        f"{STARTUP_PURGE_RESULT['ipfs_gops']} IPFS GOP rows / "
        f"{STARTUP_PURGE_RESULT['uploads_removed']} uploads / "
        f"{STARTUP_PURGE_RESULT['ring_buffer_removed']} ring buffer files / "
        f"mab_state_removed={STARTUP_PURGE_RESULT['mab_state_removed']}"
    )
    try:
        gop_anchor.start()
    except Exception as e:
        logger.warning(f"Failed to start GOP anchor on startup: {e}")
    logger.info("SecureLens started — GOP anchor + Gateway scheduler running")

@app.on_event("shutdown")
async def shutdown_event():
    if hasattr(app.state, 'scheduler'): app.state.scheduler.shutdown()
    if mab_manager: mab_manager.save_state()
    try:
        gop_anchor.stop()
    except Exception:
        pass
    if ring_buffer_manager:
        ring_buffer_manager.stop()
    logger.info("SecureLens shutdown — MAB state saved")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
