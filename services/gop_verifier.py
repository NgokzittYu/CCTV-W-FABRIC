"""
GOP 完整性验证服务
用于验证存储在 MinIO 中的 GOP 是否与区块链上的 Merkle 根匹配
"""

import hashlib
import json
import logging
from typing import Dict
from pathlib import Path

from services.minio_storage import VideoStorage
from services.merkle_utils import MerkleTree
from services.fabric_client import verify_anchor

logger = logging.getLogger(__name__)


class GOPVerifier:
    """GOP 完整性验证服务"""

    def __init__(
        self,
        storage: VideoStorage,
        fabric_env: Dict[str, str],
        orderer_ca: Path,
        org2_tls: Path,
        channel: str,
        chaincode: str,
    ):
        """
        初始化 GOP 验证器

        Args:
            storage: MinIO 存储服务实例
            fabric_env: Fabric 环境变量
            orderer_ca: Orderer CA 证书路径
            org2_tls: Org2 TLS 证书路径
            channel: Fabric 通道名称
            chaincode: 链码名称
        """
        self.storage = storage
        self.fabric_env = fabric_env
        self.orderer_ca = orderer_ca
        self.org2_tls = org2_tls
        self.channel = channel
        self.chaincode = chaincode

    def verify_gop(self, device_id: str, epoch_id: str, gop_index: int) -> dict:
        """
        验证特定 GOP 对应锚点的完整性

        Args:
            device_id: 设备 ID
            epoch_id: 时期 ID（锚点键）
            gop_index: Merkle 树中的 GOP 索引（0-based）

        Returns:
            验证结果字典，包含：
            - status: "INTACT" 或 "NOT_INTACT"
            - details: 详细信息（CID、重新计算的哈希等）
            - reason: 如果 NOT_INTACT，说明原因

        Raises:
            FileNotFoundError: 如果 Merkle 树 JSON 或 GOP 文件不存在
            ValueError: 如果 gop_index 超出范围
        """
        # 1. 从 MinIO 下载 Merkle 树 JSON
        merkle_tree_filename = f"merkle_tree_{epoch_id}.json"
        try:
            tree_data = self.storage.download_json(device_id, merkle_tree_filename)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Anchor phase incomplete: Merkle tree not found for epoch {epoch_id}"
            )

        # 2. 反序列化 Merkle 树
        tree_json = json.dumps(tree_data)
        tree = MerkleTree.from_json(tree_json)

        # 3. 获取指定索引的 CID（叶子哈希）
        if not (0 <= gop_index < len(tree._original_leaves)):
            raise ValueError(
                f"GOP index {gop_index} out of range [0, {len(tree._original_leaves)})"
            )

        cid = tree._original_leaves[gop_index]
        logger.info(f"Verifying GOP at index {gop_index}, CID: {cid[:8]}...")

        # 4. 从 MinIO 下载 GOP 字节
        try:
            gop_bytes = self.storage.download_gop(device_id, cid)
        except FileNotFoundError:
            raise FileNotFoundError(f"GOP not found: {cid}")

        # 5. 重新计算 SHA-256
        recomputed_hash = hashlib.sha256(gop_bytes).hexdigest()
        logger.debug(f"Recomputed hash: {recomputed_hash}")
        logger.debug(f"Expected CID:    {cid}")

        # 6. 生成 Merkle 证明
        proof = tree.get_proof(gop_index)
        proof_json = json.dumps(proof)

        # 7. 调用链码验证
        try:
            result_json = verify_anchor(
                self.fabric_env,
                self.orderer_ca,
                self.org2_tls,
                self.channel,
                self.chaincode,
                epoch_id,
                recomputed_hash,
                proof_json,
            )
            result = json.loads(result_json)
        except Exception as e:
            logger.error(f"Fabric verification failed: {e}")
            return {
                "status": "NOT_INTACT",
                "reason": f"Fabric verification error: {str(e)}",
                "details": {
                    "device_id": device_id,
                    "epoch_id": epoch_id,
                    "gop_index": gop_index,
                    "cid": cid,
                    "recomputed_hash": recomputed_hash,
                },
            }

        # 8. 添加详细信息并返回
        result["details"] = {
            "device_id": device_id,
            "epoch_id": epoch_id,
            "gop_index": gop_index,
            "cid": cid,
            "recomputed_hash": recomputed_hash,
            "gop_size_bytes": len(gop_bytes),
        }

        logger.info(
            f"Verification result for GOP {gop_index}: {result.get('status')}"
        )
        return result
