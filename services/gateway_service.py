"""
Gateway Service for aggregating device SegmentRoots into EpochMerkleTree.
Handles periodic blockchain anchoring and SQLite persistence.
"""

import asyncio
import sqlite3
import json
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

from services.merkle_utils import EpochMerkleTree, DeviceSegment
from services.fabric_client import submit_anchor


class GatewayService:
    """
    Manages epoch aggregation, SQLite storage, and blockchain anchoring.

    Workflow:
    1. Devices POST /report with SegmentRoots
    2. Every 30 seconds, flush_epoch() builds EpochMerkleTree
    3. Anchor EpochRoot to blockchain
    4. Save epoch data to SQLite
    """

    def __init__(self, db_path: str, fabric_config: Dict):
        """
        Args:
            db_path: Path to SQLite database file
            fabric_config: Dict with keys: env, orderer_ca, org2_tls, channel, chaincode
        """
        self._db_path = db_path
        self._fabric_config = fabric_config
        self._pending_reports: Dict[str, DeviceSegment] = {}  # device_id -> DeviceSegment
        self._lock = asyncio.Lock()  # Protect concurrent access
        self._init_database()

    def _init_database(self) -> None:
        """Create tables if they don't exist."""
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        # Epochs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS epochs (
                epoch_id TEXT PRIMARY KEY,
                epoch_root TEXT NOT NULL,
                device_count INTEGER NOT NULL,
                tx_id TEXT,
                created_at TEXT NOT NULL,
                tree_json TEXT NOT NULL
            )
        """)

        # Device reports table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS device_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                epoch_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                segment_root TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                gop_count INTEGER NOT NULL,
                semantic_summaries TEXT,
                FOREIGN KEY (epoch_id) REFERENCES epochs(epoch_id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_epoch_device
            ON device_reports(epoch_id, device_id)
        """)

        conn.commit()
        conn.close()

    async def add_device_report(self, report: Dict) -> None:
        """
        Add a device report to the current epoch.
        If device already reported in this epoch, overwrites with latest (last-write-wins).

        Args:
            report: {
                "device_id": str,
                "segment_root": str,
                "timestamp": str,
                "semantic_summaries": List[str],
                "gop_count": int
            }
        """
        device_segment = DeviceSegment(**report)
        async with self._lock:
            self._pending_reports[device_segment.device_id] = device_segment

    async def flush_epoch(self) -> Optional[str]:
        """
        Build EpochMerkleTree from pending reports, anchor to blockchain, save to DB.

        Returns:
            epoch_id if successful, None if no reports to flush
        """
        # Acquire lock and copy reports, then release before slow operations
        async with self._lock:
            if len(self._pending_reports) == 0:
                return None
            reports = list(self._pending_reports.values())
            self._pending_reports.clear()

        # Generate epoch_id
        epoch_id = f"epoch_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        # Build tree
        epoch_tree = EpochMerkleTree(epoch_id)
        for report in reports:
            epoch_tree.add_device_segment(report)
        epoch_root = epoch_tree.build_tree()

        # Anchor to blockchain (wrapped in thread pool to avoid blocking)
        try:
            result = await asyncio.to_thread(
                submit_anchor,
                env=self._fabric_config["env"],
                orderer_ca=self._fabric_config["orderer_ca"],
                org2_tls=self._fabric_config["org2_tls"],
                channel=self._fabric_config["channel"],
                chaincode=self._fabric_config["chaincode"],
                epoch_id=epoch_id,
                merkle_root=epoch_root,
                timestamp=datetime.utcnow().isoformat(),
                device_count=len(epoch_tree._devices)
            )
        except Exception as e:
            print(f"[GatewayService] Blockchain anchor failed: {e}")
            result = {"tx_id": None, "status": "failed"}

        # Save to database (wrapped in thread pool to avoid blocking)
        await asyncio.to_thread(self._save_epoch, epoch_tree, result)

        print(f"[GatewayService] Flushed {epoch_id}: {len(epoch_tree._devices)} devices, root={epoch_root[:16]}...")
        return epoch_id

    def _save_epoch(self, epoch_tree: EpochMerkleTree, anchor_result: Dict) -> None:
        """Save epoch and device reports to SQLite."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        try:
            # Save epoch
            cursor.execute("""
                INSERT INTO epochs (epoch_id, epoch_root, device_count, tx_id, created_at, tree_json)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                epoch_tree._epoch_id,
                epoch_tree._epoch_root,
                len(epoch_tree._devices),
                anchor_result.get("tx_id"),
                datetime.utcnow().isoformat(),
                epoch_tree.to_json()
            ))

            # Save device reports
            for device in epoch_tree._devices.values():
                cursor.execute("""
                    INSERT INTO device_reports
                    (epoch_id, device_id, segment_root, timestamp, gop_count, semantic_summaries)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    epoch_tree._epoch_id,
                    device.device_id,
                    device.segment_root,
                    device.timestamp,
                    device.gop_count,
                    json.dumps(device.semantic_summaries)
                ))

            conn.commit()
        finally:
            conn.close()

    def get_epoch(self, epoch_id: str) -> Optional[Dict]:
        """Retrieve epoch data from database."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT epoch_id, epoch_root, device_count, tx_id, created_at, tree_json
                FROM epochs WHERE epoch_id = ?
            """, (epoch_id,))

            row = cursor.fetchone()
            if not row:
                return None

            # Get device reports
            cursor.execute("""
                SELECT device_id, segment_root, timestamp, gop_count, semantic_summaries
                FROM device_reports WHERE epoch_id = ?
            """, (epoch_id,))

            devices = []
            for device_row in cursor.fetchall():
                devices.append({
                    "device_id": device_row[0],
                    "segment_root": device_row[1],
                    "timestamp": device_row[2],
                    "gop_count": device_row[3],
                    "semantic_summaries": json.loads(device_row[4])
                })

            return {
                "epoch_id": row[0],
                "epoch_root": row[1],
                "device_count": row[2],
                "tx_id": row[3],
                "created_at": row[4],
                "devices": devices
            }
        finally:
            conn.close()

    def list_epochs(self, limit: int = 20) -> List[Dict]:
        """List recent epochs (for debugging/demo)."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT epoch_id, epoch_root, device_count, tx_id, created_at
                FROM epochs
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))

            epochs = []
            for row in cursor.fetchall():
                epochs.append({
                    "epoch_id": row[0],
                    "epoch_root": row[1],
                    "device_count": row[2],
                    "tx_id": row[3],
                    "created_at": row[4]
                })

            return epochs
        finally:
            conn.close()

    def get_device_proof(self, epoch_id: str, device_id: str) -> Optional[Dict]:
        """Generate proof for a device in a specific epoch."""
        conn = sqlite3.connect(self._db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT tree_json FROM epochs WHERE epoch_id = ?
            """, (epoch_id,))

            row = cursor.fetchone()
            if not row:
                return None

            # Deserialize tree and generate proof
            epoch_tree = EpochMerkleTree.from_json(row[0])

            try:
                proof = epoch_tree.get_device_proof(device_id)
                return proof
            except ValueError:
                return None
        finally:
            conn.close()
