"""
MinIO 分布式对象存储服务
用于存储 GOP 视频分片和相关 JSON 数据
"""

import io
import json
import hashlib
import logging
from typing import List, Dict
from minio import Minio
from minio.error import S3Error

from services.gop_splitter import GOPData

logger = logging.getLogger(__name__)


class VideoStorage:
    """MinIO 视频存储服务，支持 GOP 分片的上传、下载和查询"""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket_name: str,
        secure: bool = False
    ):
        """
        初始化 MinIO 客户端

        Args:
            endpoint: MinIO 服务地址 (例如 "localhost:9000")
            access_key: 访问密钥
            secret_key: 密钥
            bucket_name: 存储桶名称
            secure: 是否使用 HTTPS
        """
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )
        self.bucket = bucket_name

        # 内存索引：CID → object_name 映射，用于快速查找
        self._cid_index: Dict[str, str] = {}

        # 确保 bucket 存在
        try:
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
                logger.info(f"Created bucket: {bucket_name}")
            else:
                logger.info(f"Connected to existing bucket: {bucket_name}")
        except S3Error as e:
            logger.error(f"Failed to initialize bucket {bucket_name}: {e}")
            raise

    def upload_gop(self, device_id: str, gop: GOPData) -> str:
        """
        上传 GOP 分片到 MinIO

        Args:
            device_id: 设备 ID
            gop: GOP 数据对象

        Returns:
            CID (SHA-256 hash)
        """
        # 使用已计算好的 SHA-256 作为 CID
        cid = gop.sha256_hash

        # 优化路径设计：{device_id}/t_{timestamp_int}/{cid}.h264
        timestamp_int = int(gop.start_time)
        object_name = f"{device_id}/t_{timestamp_int}/{cid}.h264"

        # 准备元数据（MinIO SDK 要求 value 为字符串）
        metadata = {
            "gop_id": str(gop.gop_id),
            "timestamp": str(gop.start_time),
            "sha256_hash": gop.sha256_hash
        }

        try:
            # 上传对象
            self.client.put_object(
                bucket_name=self.bucket,
                object_name=object_name,
                data=io.BytesIO(gop.raw_bytes),
                length=gop.byte_size,
                content_type="video/h264",
                metadata=metadata
            )

            # 上传语义 JSON（如果可用）
            if gop.semantic_fingerprint:
                semantic_filename = f"{cid}_semantic.json"
                semantic_path = f"{device_id}/t_{timestamp_int}/{semantic_filename}"

                # 构建语义 JSON 数据
                semantic_data = {
                    "gop_id": gop.semantic_fingerprint.gop_id,
                    "timestamp": gop.semantic_fingerprint.timestamp,
                    "objects": gop.semantic_fingerprint.objects,
                    "total_count": gop.semantic_fingerprint.total_count,
                    "semantic_hash": gop.semantic_fingerprint.semantic_hash
                }

                # 序列化并上传
                semantic_json = json.dumps(semantic_data, indent=2)
                self.client.put_object(
                    self.bucket,
                    semantic_path,
                    io.BytesIO(semantic_json.encode('utf-8')),
                    len(semantic_json),
                    content_type='application/json'
                )
                logger.debug(f"Uploaded semantic JSON: {semantic_path}")

            # 记录到内存索引
            self._cid_index[cid] = object_name

            logger.debug(f"Uploaded GOP {gop.gop_id} as {object_name} (CID: {cid[:8]}...)")
            return cid

        except S3Error as e:
            logger.error(f"Failed to upload GOP {gop.gop_id}: {e}")
            raise

    def download_gop(self, device_id: str, cid: str) -> bytes:
        """
        下载 GOP 分片（性能优化版：优先使用内存索引）

        Args:
            device_id: 设备 ID
            cid: Content ID (SHA-256 hash)

        Returns:
            GOP 原始字节数据

        Raises:
            FileNotFoundError: 如果找不到对应的 GOP
        """
        # 优先查内存索引
        object_name = self._cid_index.get(cid)

        if object_name:
            try:
                response = self.client.get_object(self.bucket, object_name)
                data = response.read()
                response.close()
                response.release_conn()
                logger.debug(f"Downloaded GOP from index: {object_name}")
                return data
            except S3Error as e:
                logger.warning(f"Index hit but download failed: {e}, falling back to search")

        # Fallback: 遍历查找（兼容外部上传的数据）
        try:
            objects = self.client.list_objects(
                self.bucket,
                prefix=f"{device_id}/",
                recursive=True
            )

            for obj in objects:
                if obj.object_name.endswith(f"{cid}.h264"):
                    response = self.client.get_object(self.bucket, obj.object_name)
                    data = response.read()
                    response.close()
                    response.release_conn()

                    # 更新索引
                    self._cid_index[cid] = obj.object_name
                    logger.debug(f"Downloaded GOP via search: {obj.object_name}")
                    return data

            raise FileNotFoundError(f"GOP with CID {cid} not found for device {device_id}")

        except S3Error as e:
            logger.error(f"Failed to download GOP {cid}: {e}")
            raise

    def list_gops(
        self,
        device_id: str,
        start_time: float,
        end_time: float
    ) -> List[dict]:
        """
        列出指定时间范围内的所有 GOP（性能优化版：从路径解析时间戳）

        Args:
            device_id: 设备 ID
            start_time: 开始时间戳（Unix 时间）
            end_time: 结束时间戳（Unix 时间）

        Returns:
            GOP 信息列表，每项包含 object_name, cid, timestamp, size
        """
        result = []

        try:
            objects = self.client.list_objects(
                self.bucket,
                prefix=f"{device_id}/",
                recursive=True
            )

            for obj in objects:
                # 跳过非 h264 文件（如 JSON 索引文件）
                if not obj.object_name.endswith(".h264"):
                    continue

                # 从路径解析时间戳：{device_id}/t_{timestamp_int}/{cid}.h264
                try:
                    parts = obj.object_name.split("/")
                    if len(parts) >= 3 and parts[1].startswith("t_"):
                        timestamp_int = int(parts[1][2:])  # 去掉 "t_" 前缀

                        # 时间范围筛选
                        if start_time <= timestamp_int <= end_time:
                            # 提取 CID（文件名去掉 .h264 后缀）
                            cid = parts[2].replace(".h264", "")

                            result.append({
                                "object_name": obj.object_name,
                                "cid": cid,
                                "timestamp": timestamp_int,
                                "size": obj.size
                            })
                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse object path {obj.object_name}: {e}")
                    continue

            logger.info(f"Found {len(result)} GOPs for device {device_id} in time range [{start_time}, {end_time}]")
            return result

        except S3Error as e:
            logger.error(f"Failed to list GOPs: {e}")
            raise

    def upload_json(self, device_id: str, filename: str, data: dict) -> str:
        """
        上传 JSON 数据到 MinIO

        Args:
            device_id: 设备 ID
            filename: 文件名
            data: 要上传的字典数据

        Returns:
            JSON 内容的 SHA-256 hash
        """
        # 序列化 JSON
        json_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        json_hash = hashlib.sha256(json_bytes).hexdigest()

        object_name = f"{device_id}/{filename}"

        try:
            self.client.put_object(
                bucket_name=self.bucket,
                object_name=object_name,
                data=io.BytesIO(json_bytes),
                length=len(json_bytes),
                content_type="application/json"
            )

            logger.info(f"Uploaded JSON: {object_name} (hash: {json_hash[:8]}...)")
            return json_hash

        except S3Error as e:
            logger.error(f"Failed to upload JSON {filename}: {e}")
            raise

    def download_json(self, device_id: str, filename: str) -> dict:
        """
        从 MinIO 下载 JSON 数据

        Args:
            device_id: 设备 ID
            filename: 文件名

        Returns:
            解析后的字典数据

        Raises:
            FileNotFoundError: 如果文件不存在
        """
        object_name = f"{device_id}/{filename}"

        try:
            response = self.client.get_object(self.bucket, object_name)
            json_bytes = response.read()
            response.close()
            response.release_conn()

            data = json.loads(json_bytes.decode("utf-8"))
            logger.info(f"Downloaded JSON: {object_name}")
            return data

        except S3Error as e:
            if e.code == "NoSuchKey":
                raise FileNotFoundError(f"JSON file {filename} not found for device {device_id}")
            logger.error(f"Failed to download JSON {filename}: {e}")
            raise

    def save_cid_index(self, device_id: str) -> None:
        """
        持久化 CID 索引到 MinIO（可选功能）

        Args:
            device_id: 设备 ID
        """
        if not self._cid_index:
            logger.warning("CID index is empty, skipping save")
            return

        self.upload_json(device_id, "cid_index.json", self._cid_index)
        logger.info(f"Saved CID index with {len(self._cid_index)} entries")

    def load_cid_index(self, device_id: str) -> None:
        """
        从 MinIO 加载 CID 索引（可选功能）

        Args:
            device_id: 设备 ID
        """
        try:
            index_data = self.download_json(device_id, "cid_index.json")
            self._cid_index.update(index_data)
            logger.info(f"Loaded CID index with {len(index_data)} entries")
        except FileNotFoundError:
            logger.info("No existing CID index found, starting fresh")
        except Exception as e:
            logger.warning(f"Failed to load CID index: {e}")
