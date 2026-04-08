"""
SQLite Video Store — 视频存证与验真索引层

Tables:
  - videos: 存证视频元数据 (id, device_id, filename, gop_count, merkle_root, tx_id, block_number, ...)
  - video_gops: 每个 GOP 的哈希信息 (video_id, gop_index, sha256, vif, ...)
  - verify_history: 验真历史记录
"""
import json
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional


DB_PATH = Path("data/video_store.db")

_local = threading.local()


def _get_conn() -> sqlite3.Connection:
    """Per-thread SQLite connection with row_factory."""
    if not hasattr(_local, "conn") or _local.conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn


def init_db():
    """Create tables if not exist."""
    conn = _get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS videos (
        id            TEXT PRIMARY KEY,
        device_id     TEXT NOT NULL,
        filename      TEXT NOT NULL,
        file_size     INTEGER DEFAULT 0,
        gop_count     INTEGER DEFAULT 0,
        merkle_root   TEXT,
        tx_id         TEXT,
        block_number  INTEGER,
        status        TEXT DEFAULT 'anchored',
        created_at    REAL NOT NULL
    );

    CREATE TABLE IF NOT EXISTS video_gops (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id   TEXT NOT NULL REFERENCES videos(id),
        gop_index  INTEGER NOT NULL,
        sha256     TEXT NOT NULL,
        vif        TEXT,
        start_time REAL,
        end_time   REAL,
        frame_count INTEGER,
        byte_size  INTEGER
    );

    CREATE INDEX IF NOT EXISTS idx_video_gops_video ON video_gops(video_id);

    CREATE TABLE IF NOT EXISTS verify_history (
        id             TEXT PRIMARY KEY,
        original_video_id TEXT NOT NULL,
        uploaded_filename TEXT,
        overall_status TEXT NOT NULL,
        overall_risk   REAL DEFAULT 0.0,
        gop_results    TEXT,
        created_at     REAL NOT NULL
    );
    """)
    conn.commit()


# ── Video CRUD ─────────────────────────────────────────────────────

def insert_video(
    video_id: str,
    device_id: str,
    filename: str,
    file_size: int,
    gop_count: int,
    merkle_root: str,
    tx_id: str,
    block_number: Optional[int],
) -> Dict:
    """Insert a new video record."""
    conn = _get_conn()
    now = time.time()
    conn.execute(
        """INSERT INTO videos (id, device_id, filename, file_size, gop_count,
           merkle_root, tx_id, block_number, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (video_id, device_id, filename, file_size, gop_count,
         merkle_root, tx_id, block_number, now),
    )
    conn.commit()
    return {
        "id": video_id,
        "device_id": device_id,
        "filename": filename,
        "file_size": file_size,
        "gop_count": gop_count,
        "merkle_root": merkle_root,
        "tx_id": tx_id,
        "block_number": block_number,
        "status": "anchored",
        "created_at": now,
    }


def insert_video_gops(video_id: str, gops_data: List[Dict]):
    """Batch-insert GOP records."""
    conn = _get_conn()
    conn.executemany(
        """INSERT INTO video_gops
           (video_id, gop_index, sha256, vif, start_time, end_time, frame_count, byte_size)
           VALUES (:video_id, :gop_index, :sha256, :vif, :start_time, :end_time, :frame_count, :byte_size)""",
        gops_data,
    )
    conn.commit()


def list_videos() -> List[Dict]:
    """List all videos ordered by creation time desc."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM videos ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_video(video_id: str) -> Optional[Dict]:
    """Get single video by id."""
    conn = _get_conn()
    row = conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
    return dict(row) if row else None


def get_video_gops(video_id: str) -> List[Dict]:
    """Get all GOPs for a video."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM video_gops WHERE video_id = ? ORDER BY gop_index",
        (video_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ── Verify History ─────────────────────────────────────────────────

def insert_verify_record(
    original_video_id: str,
    uploaded_filename: str,
    overall_status: str,
    overall_risk: float,
    gop_results: List[Dict],
) -> Dict:
    """Insert a verification history record."""
    conn = _get_conn()
    record_id = f"vfy-{uuid.uuid4().hex[:12]}"
    now = time.time()
    conn.execute(
        """INSERT INTO verify_history
           (id, original_video_id, uploaded_filename, overall_status, overall_risk, gop_results, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (record_id, original_video_id, uploaded_filename,
         overall_status, overall_risk, json.dumps(gop_results, ensure_ascii=False), now),
    )
    conn.commit()
    return {
        "id": record_id,
        "original_video_id": original_video_id,
        "uploaded_filename": uploaded_filename,
        "overall_status": overall_status,
        "overall_risk": overall_risk,
        "gop_results": gop_results,
        "created_at": now,
    }


def list_verify_history(limit: int = 50) -> List[Dict]:
    """List verification history."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM verify_history ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        if d.get("gop_results"):
            d["gop_results"] = json.loads(d["gop_results"])
        results.append(d)
    return results


# Initialize on import
init_db()
