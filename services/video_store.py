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

from services.gop_timing import normalize_gop_bounds

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
        verify_mode    TEXT DEFAULT 'original_video',
        reference_device_id TEXT,
        reference_start_time REAL,
        reference_end_time REAL,
        gap_flag       INTEGER DEFAULT 0,
        matched_gop_count INTEGER DEFAULT 0,
        overall_status TEXT NOT NULL,
        overall_risk   REAL DEFAULT 0.0,
        gop_results    TEXT,
        created_at     REAL NOT NULL
    );
    """)
    _ensure_verify_history_columns(conn)
    conn.commit()


def _ensure_verify_history_columns(conn: sqlite3.Connection):
    """Backfill newer verify_history columns for existing databases."""
    expected_columns = {
        "verify_mode": "TEXT DEFAULT 'original_video'",
        "reference_device_id": "TEXT",
        "reference_start_time": "REAL",
        "reference_end_time": "REAL",
        "gap_flag": "INTEGER DEFAULT 0",
        "matched_gop_count": "INTEGER DEFAULT 0",
    }
    existing = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(verify_history)").fetchall()
    }
    for column, column_type in expected_columns.items():
        if column in existing:
            continue
        conn.execute(f"ALTER TABLE verify_history ADD COLUMN {column} {column_type}")


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
    created_at: Optional[float] = None,
) -> Dict:
    """Insert a new video record."""
    conn = _get_conn()
    now = created_at if created_at is not None else time.time()
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


def get_device_gops_by_time(device_id: str, start_time: float, end_time: float) -> List[Dict]:
    """Get stored GOP rows for a device in a wall-clock time range."""
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT g.*, v.device_id
        FROM video_gops g
        JOIN videos v ON v.id = g.video_id
        WHERE v.device_id = ?
          AND COALESCE(g.start_time, 0) <= ?
          AND COALESCE(g.end_time, COALESCE(g.start_time, 0)) >= ?
        ORDER BY COALESCE(g.start_time, 0) ASC, g.gop_index ASC
        """,
        (device_id, end_time, start_time),
    ).fetchall()
    return [dict(r) for r in rows]


def backfill_live_gop_wallclock_times(ipfs_index_db_path: str = "data/ipfs_index.db") -> Dict[str, int]:
    """Repair live GOP rows onto one continuous wall-clock timeline.

    Live GOPs carry stream-PTS timestamps. Those are continuous across batches,
    but older implementations either stored them directly or reprojected each
    5-GOP batch independently, creating artificial gaps. This function rebuilds
    wall-clock times from packet PTS metadata and stitches consecutive batches
    into one continuous timeline per live session.
    """
    conn = _get_conn()
    ipfs_conn = sqlite3.connect(ipfs_index_db_path)
    ipfs_conn.row_factory = sqlite3.Row
    touched_videos = 0
    touched_gops = 0

    try:
        videos = conn.execute(
            """
            SELECT DISTINCT v.id, v.device_id, v.created_at
            FROM videos v
            JOIN video_gops g ON g.video_id = v.id
            WHERE v.filename LIKE 'live_%'
            ORDER BY v.created_at ASC
            """
        ).fetchall()

        last_relative_end = None
        last_mapped_end = None

        for video in videos:
            gops = conn.execute(
                """
                SELECT g.id AS gop_row_id,
                       g.sha256
                FROM video_gops g
                WHERE g.video_id = ?
                ORDER BY g.gop_index ASC
                """,
                (video["id"],),
            ).fetchall()
            if not gops:
                continue

            rel_bounds = []
            for gop in gops:
                index_row = ipfs_conn.execute(
                    """
                    SELECT packet_pts_json, time_base_num, time_base_den
                    FROM gop_index
                    WHERE device_id = ? AND sha256_hash = ?
                    """,
                    (video["device_id"], gop["sha256"]),
                ).fetchone()
                if not index_row:
                    continue
                pts_list = json.loads(index_row["packet_pts_json"]) if index_row["packet_pts_json"] else []
                pts_values = [p for p in pts_list if p is not None]
                if not pts_values:
                    continue
                time_base_num = int(index_row["time_base_num"] or 1)
                time_base_den = int(index_row["time_base_den"] or 1)
                rel_start = min(pts_values) * time_base_num / time_base_den
                _, rel_end, rel_duration = normalize_gop_bounds(
                    rel_start,
                    max(pts_values) * time_base_num / time_base_den,
                    packet_pts=pts_list,
                    time_base_num=time_base_num,
                    time_base_den=time_base_den,
                )
                rel_bounds.append(
                    {
                        "gop_row_id": gop["gop_row_id"],
                        "sha256": gop["sha256"],
                        "rel_start": rel_start,
                        "rel_end": rel_end,
                        "rel_duration": rel_duration,
                    }
                )

            if not rel_bounds:
                continue

            first_rel_start = rel_bounds[0]["rel_start"]
            video_rel_end = max(item["rel_end"] for item in rel_bounds)
            should_rebase = (
                last_relative_end is None
                or last_mapped_end is None
                or first_rel_start < (last_relative_end - 1.0)
            )
            if should_rebase:
                offset = float(video["created_at"]) - video_rel_end
            else:
                offset = last_mapped_end - last_relative_end

            for item in rel_bounds:
                abs_start = item["rel_start"] + offset
                abs_end = item["rel_end"] + offset
                conn.execute(
                    """
                    UPDATE video_gops
                    SET start_time = ?, end_time = ?
                    WHERE id = ?
                    """,
                    (abs_start, abs_end, item["gop_row_id"]),
                )
                ipfs_conn.execute(
                    """
                    UPDATE gop_index
                    SET timestamp = ?,
                        duration_seconds = ?
                    WHERE device_id = ?
                      AND sha256_hash = ?
                    """,
                    (abs_start, item["rel_duration"], video["device_id"], item["sha256"]),
                )
                touched_gops += 1

            mapped_video_end = video_rel_end + offset
            conn.execute(
                "UPDATE videos SET created_at = ? WHERE id = ?",
                (mapped_video_end, video["id"]),
            )
            last_relative_end = video_rel_end
            last_mapped_end = mapped_video_end
            touched_videos += 1

        conn.commit()
        ipfs_conn.commit()
        return {"videos": touched_videos, "gops": touched_gops}
    finally:
        ipfs_conn.close()


def repair_future_live_timestamps(
    ipfs_index_db_path: str = "data/ipfs_index.db",
    *,
    future_threshold_seconds: float = 300.0,
) -> Dict[str, float]:
    """如果 live 时间轴整体漂到未来，将其整体拉回当前墙上时钟。"""
    conn = _get_conn()
    ipfs_conn = sqlite3.connect(ipfs_index_db_path)
    ipfs_conn.row_factory = sqlite3.Row

    shifted_videos = 0
    shifted_gops = 0
    shifted_index_rows = 0
    applied_delta = 0.0

    try:
        now = time.time()
        live_videos = conn.execute(
            """
            SELECT id, device_id, created_at
            FROM videos
            WHERE filename LIKE 'live_%'
            ORDER BY created_at DESC
            """
        ).fetchall()
        if not live_videos:
            return {"videos": 0, "gops": 0, "index_rows": 0, "delta_seconds": 0.0}

        latest_created_at = float(live_videos[0]["created_at"] or 0.0)
        if latest_created_at <= (now + future_threshold_seconds):
            return {"videos": 0, "gops": 0, "index_rows": 0, "delta_seconds": 0.0}

        applied_delta = latest_created_at - now
        affected_ids = [row["id"] for row in live_videos if float(row["created_at"] or 0.0) > (now + future_threshold_seconds)]
        affected_devices = sorted({row["device_id"] for row in live_videos})

        for video_id in affected_ids:
            conn.execute(
                "UPDATE videos SET created_at = created_at - ? WHERE id = ?",
                (applied_delta, video_id),
            )
            shifted_videos += 1

        for video_id in affected_ids:
            cursor = conn.execute(
                """
                UPDATE video_gops
                SET start_time = CASE WHEN start_time IS NULL THEN NULL ELSE start_time - ? END,
                    end_time = CASE WHEN end_time IS NULL THEN NULL ELSE end_time - ? END
                WHERE video_id = ?
                """,
                (applied_delta, applied_delta, video_id),
            )
            shifted_gops += cursor.rowcount or 0

        for device_id in affected_devices:
            cursor = ipfs_conn.execute(
                """
                UPDATE gop_index
                SET timestamp = timestamp - ?
                WHERE device_id = ?
                  AND timestamp > ?
                """,
                (applied_delta, device_id, now + future_threshold_seconds),
            )
            shifted_index_rows += cursor.rowcount or 0

        conn.commit()
        ipfs_conn.commit()
        return {
            "videos": shifted_videos,
            "gops": shifted_gops,
            "index_rows": shifted_index_rows,
            "delta_seconds": applied_delta,
        }
    finally:
        ipfs_conn.close()


# ── Verify History ─────────────────────────────────────────────────

def insert_verify_record(
    original_video_id: str,
    uploaded_filename: str,
    overall_status: str,
    overall_risk: float,
    gop_results: List[Dict],
    *,
    verify_mode: str = "original_video",
    reference_device_id: Optional[str] = None,
    reference_start_time: Optional[float] = None,
    reference_end_time: Optional[float] = None,
    gap_flag: int = 0,
    matched_gop_count: int = 0,
) -> Dict:
    """Insert a verification history record."""
    conn = _get_conn()
    record_id = f"vfy-{uuid.uuid4().hex[:12]}"
    now = time.time()
    conn.execute(
        """INSERT INTO verify_history
           (id, original_video_id, uploaded_filename, verify_mode, reference_device_id,
            reference_start_time, reference_end_time, gap_flag, matched_gop_count,
            overall_status, overall_risk, gop_results, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (record_id, original_video_id, uploaded_filename,
         verify_mode, reference_device_id, reference_start_time, reference_end_time,
         int(gap_flag), int(matched_gop_count),
         overall_status, overall_risk, json.dumps(gop_results, ensure_ascii=False), now),
    )
    conn.commit()
    return {
        "id": record_id,
        "original_video_id": original_video_id,
        "uploaded_filename": uploaded_filename,
        "verify_mode": verify_mode,
        "reference_device_id": reference_device_id,
        "reference_start_time": reference_start_time,
        "reference_end_time": reference_end_time,
        "gap_flag": int(gap_flag),
        "matched_gop_count": int(matched_gop_count),
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
