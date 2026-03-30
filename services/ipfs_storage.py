"""
IPFS 去中心化内容寻址存储服务
用于存储 GOP 视频分片和相关 JSON 数据

替代原 MinIO 对象存储，提供相同的 VideoStorage 接口。
IPFS 原生内容寻址保证：CID = 内容哈希 = 完整性证明。
"""

import io
import json
import hashlib
import logging
import sqlite3
import time
from pathlib import Path
from typing import List, Dict, Optional

import requests

from services.gop_splitter import GOPData

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# IPFS HTTP API 客户端（轻量级，无第三方依赖 fallback）
# ---------------------------------------------------------------------------


class IPFSClient:
    """轻量级 IPFS HTTP API 客户端，包装 Kubo RPC API"""

    def __init__(self, api_url: str = "http://localhost:5001"):
        self.api_url = api_url.rstrip("/")
        self._session = requests.Session()

    def add_bytes(self, data: bytes, pin: bool = True, cid_version: int = 1) -> str:
        """
        上传字节数据到 IPFS

        Args:
            data: 原始字节
            pin: 是否 Pin（防 GC 清除）
            cid_version: CID 版本（1 = CIDv1）

        Returns:
            IPFS CID 字符串
        """
        url = f"{self.api_url}/api/v0/add"
        params = {
            "pin": str(pin).lower(),
            "cid-version": cid_version,
            "hash": "sha2-256",
        }
        files = {"file": ("data", io.BytesIO(data))}

        resp = self._session.post(url, params=params, files=files, timeout=60)
        resp.raise_for_status()

        result = resp.json()
        return result["Hash"]

    def cat(self, cid: str) -> bytes:
        """
        从 IPFS 下载内容

        Args:
            cid: IPFS CID

        Returns:
            文件内容字节

        Raises:
            FileNotFoundError: CID 不存在或不可达
        """
        url = f"{self.api_url}/api/v0/cat"
        params = {"arg": cid}

        try:
            resp = self._session.post(url, params=params, timeout=120)
            resp.raise_for_status()
            return resp.content
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 500:
                raise FileNotFoundError(f"IPFS content not found: {cid}") from e
            raise

    def pin_add(self, cid: str) -> None:
        """显式 Pin 一个 CID"""
        url = f"{self.api_url}/api/v0/pin/add"
        params = {"arg": cid}
        resp = self._session.post(url, params=params, timeout=60)
        resp.raise_for_status()

    def pin_ls(self, cid: Optional[str] = None) -> List[str]:
        """列出已 Pin 的 CID"""
        url = f"{self.api_url}/api/v0/pin/ls"
        params = {"type": "recursive"}
        if cid:
            params["arg"] = cid

        resp = self._session.post(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return list(data.get("Keys", {}).keys())

    def id(self) -> Dict:
        """获取节点信息"""
        url = f"{self.api_url}/api/v0/id"
        resp = self._session.post(url, timeout=10)
        resp.raise_for_status()
        return resp.json()

    def repo_stat(self) -> Dict:
        """获取仓库统计"""
        url = f"{self.api_url}/api/v0/repo/stat"
        resp = self._session.post(url, timeout=10)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# SQLite 索引管理
# ---------------------------------------------------------------------------


class IPFSIndex:
    """SQLite 索引，管理 IPFS CID 与设备/时间戳的映射关系"""

    def __init__(self, db_path: str = "data/ipfs_index.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        """创建索引表"""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS gop_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                gop_id INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                ipfs_cid TEXT NOT NULL,
                sha256_hash TEXT NOT NULL,
                byte_size INTEGER,
                content_type TEXT DEFAULT 'video/h264',
                created_at REAL DEFAULT (strftime('%s', 'now')),
                UNIQUE(device_id, ipfs_cid)
            );

            CREATE INDEX IF NOT EXISTS idx_gop_device_time
                ON gop_index(device_id, timestamp);

            CREATE TABLE IF NOT EXISTS json_index (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                ipfs_cid TEXT NOT NULL,
                sha256_hash TEXT NOT NULL,
                created_at REAL DEFAULT (strftime('%s', 'now')),
                UNIQUE(device_id, filename)
            );
        """)
        self._conn.commit()
        logger.info(f"IPFS index initialized: {self.db_path}")

    def insert_gop(
        self,
        device_id: str,
        gop_id: int,
        timestamp: float,
        ipfs_cid: str,
        sha256_hash: str,
        byte_size: int,
    ):
        """记录 GOP 上传信息"""
        self._conn.execute(
            """INSERT OR REPLACE INTO gop_index
               (device_id, gop_id, timestamp, ipfs_cid, sha256_hash, byte_size)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (device_id, gop_id, timestamp, ipfs_cid, sha256_hash, byte_size),
        )
        self._conn.commit()

    def query_gops(
        self,
        device_id: str,
        start_time: float,
        end_time: float,
    ) -> List[Dict]:
        """按时间范围查询 GOP"""
        cursor = self._conn.execute(
            """SELECT device_id, gop_id, timestamp, ipfs_cid, sha256_hash, byte_size
               FROM gop_index
               WHERE device_id = ? AND timestamp BETWEEN ? AND ?
               ORDER BY timestamp ASC""",
            (device_id, start_time, end_time),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_gop_cid(self, device_id: str, sha256_hash: str) -> Optional[str]:
        """通过 SHA-256 查找 IPFS CID"""
        cursor = self._conn.execute(
            """SELECT ipfs_cid FROM gop_index
               WHERE device_id = ? AND sha256_hash = ?""",
            (device_id, sha256_hash),
        )
        row = cursor.fetchone()
        return row["ipfs_cid"] if row else None

    def insert_json(
        self,
        device_id: str,
        filename: str,
        ipfs_cid: str,
        sha256_hash: str,
    ):
        """记录 JSON 上传信息"""
        self._conn.execute(
            """INSERT OR REPLACE INTO json_index
               (device_id, filename, ipfs_cid, sha256_hash)
               VALUES (?, ?, ?, ?)""",
            (device_id, filename, ipfs_cid, sha256_hash),
        )
        self._conn.commit()

    def get_json_cid(self, device_id: str, filename: str) -> Optional[str]:
        """查找 JSON 文件的 IPFS CID"""
        cursor = self._conn.execute(
            """SELECT ipfs_cid FROM json_index
               WHERE device_id = ? AND filename = ?""",
            (device_id, filename),
        )
        row = cursor.fetchone()
        return row["ipfs_cid"] if row else None

    def close(self):
        """关闭数据库连接"""
        self._conn.close()


# ---------------------------------------------------------------------------
# VideoStorage — 对外接口保持不变
# ---------------------------------------------------------------------------


class VideoStorage:
    """IPFS 视频存储服务，支持 GOP 分片的上传、下载和查询

    替代原 MinIO VideoStorage，接口签名保持一致。
    IPFS 内容寻址天然保证数据完整性：CID = SHA-256 multihash。
    """

    def __init__(
        self,
        api_url: str = "http://localhost:5001",
        gateway_url: str = "http://localhost:8080",
        pin_enabled: bool = True,
        index_db_path: str = "data/ipfs_index.db",
    ):
        """
        初始化 IPFS 存储客户端

        Args:
            api_url: IPFS Kubo API 地址 (例如 "http://localhost:5001")
            gateway_url: IPFS HTTP Gateway 地址 (用于 Web 预览)
            pin_enabled: 是否自动 Pin 上传内容
            index_db_path: SQLite 索引数据库路径
        """
        self.client = IPFSClient(api_url)
        self.gateway_url = gateway_url.rstrip("/")
        self.pin_enabled = pin_enabled
        self._index = IPFSIndex(index_db_path)

        # 验证 IPFS 节点连接
        try:
            node_info = self.client.id()
            peer_id = node_info.get("ID", "unknown")
            logger.info(f"Connected to IPFS node: {peer_id}")
        except Exception as e:
            logger.error(f"Failed to connect to IPFS node at {api_url}: {e}")
            raise

    def upload_gop(self, device_id: str, gop: GOPData) -> str:
        """
        上传 GOP 分片到 IPFS

        Args:
            device_id: 设备 ID
            gop: GOP 数据对象

        Returns:
            IPFS CID (CIDv1, SHA-256 multihash)
        """
        try:
            # 上传 GOP 原始字节到 IPFS
            ipfs_cid = self.client.add_bytes(
                gop.raw_bytes,
                pin=self.pin_enabled,
                cid_version=1,
            )

            # 记录到 SQLite 索引
            self._index.insert_gop(
                device_id=device_id,
                gop_id=gop.gop_id,
                timestamp=gop.start_time,
                ipfs_cid=ipfs_cid,
                sha256_hash=gop.sha256_hash,
                byte_size=gop.byte_size,
            )

            # 上传语义 JSON（如果可用）
            if gop.semantic_fingerprint:
                semantic_data = {
                    "gop_id": gop.semantic_fingerprint.gop_id,
                    "timestamp": gop.semantic_fingerprint.timestamp,
                    "objects": gop.semantic_fingerprint.objects,
                    "total_count": gop.semantic_fingerprint.total_count,
                    "semantic_hash": gop.semantic_fingerprint.semantic_hash,
                }
                semantic_json = json.dumps(semantic_data, indent=2)
                sem_cid = self.client.add_bytes(
                    semantic_json.encode("utf-8"),
                    pin=self.pin_enabled,
                    cid_version=1,
                )
                # 索引语义 JSON
                sem_filename = f"{gop.sha256_hash}_semantic.json"
                sem_hash = hashlib.sha256(semantic_json.encode("utf-8")).hexdigest()
                self._index.insert_json(device_id, sem_filename, sem_cid, sem_hash)
                logger.debug(f"Uploaded semantic JSON: CID={sem_cid}")

            logger.debug(
                f"Uploaded GOP {gop.gop_id} to IPFS "
                f"(CID: {ipfs_cid}, SHA-256: {gop.sha256_hash[:8]}...)"
            )
            return ipfs_cid

        except Exception as e:
            logger.error(f"Failed to upload GOP {gop.gop_id} to IPFS: {e}")
            raise

    def download_gop(self, device_id: str, cid: str) -> bytes:
        """
        从 IPFS 下载 GOP 分片

        IPFS 协议保证：cat(CID) 返回的内容哈希一定匹配 CID，
        即内容完整性在协议层已被验证。

        Args:
            device_id: 设备 ID（保持接口兼容，IPFS 下载只需 CID）
            cid: IPFS CID 或 SHA-256 hash

        Returns:
            GOP 原始字节数据

        Raises:
            FileNotFoundError: 如果 CID 不存在或不可达
        """
        # 如果传入的是 SHA-256 hex（兼容旧代码），查索引转换为 IPFS CID
        ipfs_cid = cid
        if len(cid) == 64 and all(c in "0123456789abcdef" for c in cid):
            looked_up = self._index.get_gop_cid(device_id, cid)
            if looked_up:
                ipfs_cid = looked_up
                logger.debug(f"Resolved SHA-256 {cid[:8]}... → IPFS CID {ipfs_cid}")
            else:
                raise FileNotFoundError(
                    f"No IPFS CID found for SHA-256 {cid} (device: {device_id})"
                )

        try:
            data = self.client.cat(ipfs_cid)
            logger.debug(f"Downloaded GOP from IPFS: CID={ipfs_cid}")
            return data
        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to download GOP {ipfs_cid} from IPFS: {e}")
            raise

    def list_gops(
        self,
        device_id: str,
        start_time: float,
        end_time: float,
    ) -> List[dict]:
        """
        列出指定时间范围内的所有 GOP

        通过 SQLite 索引查询，比 MinIO 遍历 bucket 更高效。

        Args:
            device_id: 设备 ID
            start_time: 开始时间戳（Unix 时间）
            end_time: 结束时间戳（Unix 时间）

        Returns:
            GOP 信息列表，每项包含 ipfs_cid, sha256_hash, timestamp, byte_size
        """
        results = self._index.query_gops(device_id, start_time, end_time)
        logger.info(
            f"Found {len(results)} GOPs for device {device_id} "
            f"in time range [{start_time}, {end_time}]"
        )
        return results

    def upload_json(self, device_id: str, filename: str, data: dict) -> str:
        """
        上传 JSON 数据到 IPFS

        Args:
            device_id: 设备 ID
            filename: 逻辑文件名（用于索引查找）
            data: 要上传的字典数据

        Returns:
            JSON 内容的 SHA-256 hash（保持向后兼容）
        """
        json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        json_hash = hashlib.sha256(json_bytes).hexdigest()

        try:
            ipfs_cid = self.client.add_bytes(
                json_bytes,
                pin=self.pin_enabled,
                cid_version=1,
            )

            # 索引: device_id + filename → IPFS CID
            self._index.insert_json(device_id, filename, ipfs_cid, json_hash)

            logger.info(f"Uploaded JSON to IPFS: {filename} (CID: {ipfs_cid})")
            return json_hash

        except Exception as e:
            logger.error(f"Failed to upload JSON {filename} to IPFS: {e}")
            raise

    def download_json(self, device_id: str, filename: str) -> dict:
        """
        从 IPFS 下载 JSON 数据

        Args:
            device_id: 设备 ID
            filename: 逻辑文件名

        Returns:
            解析后的字典数据

        Raises:
            FileNotFoundError: 如果文件不存在
        """
        ipfs_cid = self._index.get_json_cid(device_id, filename)
        if not ipfs_cid:
            raise FileNotFoundError(
                f"JSON file {filename} not found for device {device_id}"
            )

        try:
            json_bytes = self.client.cat(ipfs_cid)
            data = json.loads(json_bytes.decode("utf-8"))
            logger.info(f"Downloaded JSON from IPFS: {filename} (CID: {ipfs_cid})")
            return data
        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Failed to download JSON {filename} from IPFS: {e}")
            raise

    def pin_cid(self, cid: str) -> None:
        """
        显式 Pin 一个 CID，防止 IPFS GC 清除

        Args:
            cid: IPFS CID
        """
        self.client.pin_add(cid)
        logger.info(f"Pinned CID: {cid}")

    def get_node_stats(self) -> Dict:
        """
        获取 IPFS 节点存储统计

        Returns:
            包含 RepoSize, StorageMax, NumObjects 等信息的字典
        """
        try:
            stats = self.client.repo_stat()
            return {
                "repo_size": stats.get("RepoSize", 0),
                "storage_max": stats.get("StorageMax", 0),
                "num_objects": stats.get("NumObjects", 0),
                "repo_path": stats.get("RepoPath", ""),
            }
        except Exception as e:
            logger.error(f"Failed to get IPFS node stats: {e}")
            return {}

    def get_gateway_url(self, cid: str) -> str:
        """
        获取内容的 HTTP Gateway URL（用于 Web 面板预览）

        Args:
            cid: IPFS CID

        Returns:
            Gateway URL 字符串
        """
        return f"{self.gateway_url}/ipfs/{cid}"
