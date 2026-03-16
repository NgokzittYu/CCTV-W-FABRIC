"""
语义指纹服务 - 使用 YOLOv8 从 GOP 关键帧提取语义内容

该模块提供基于目标检测的语义指纹功能：
- 使用 YOLOv8-nano 检测关键帧中的对象
- 生成确定性 JSON 表示（对象计数）
- 计算语义哈希用于内容验证
- 检测可能逃避感知哈希的语义篡改

设计特点：
- 延迟加载单例 YOLO 模型（最小化开销）
- 线程安全的模型访问
- 优雅降级（推理失败不影响 GOP 构建）
- 确定性哈希（相同内容 → 相同哈希）
"""

import hashlib
import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

import numpy as np
from ultralytics import YOLO

from config import SETTINGS

logger = logging.getLogger(__name__)


@dataclass
class SemanticFingerprint:
    """
    语义指纹数据结构

    包含从 GOP 关键帧提取的语义信息：
    - 对象计数（按类别）
    - 确定性 JSON 表示
    - SHA-256 语义哈希
    """
    gop_id: int
    timestamp: str  # ISO 8601 格式
    objects: Dict[str, int]  # {"person": 3, "car": 2}
    total_count: int
    json_str: str  # 确定性序列化的 JSON
    semantic_hash: str  # SHA-256(json_str)


class SemanticExtractor:
    """
    语义提取器 - 使用 YOLOv8 从关键帧提取对象信息

    实现为线程安全的单例模式：
    - 模型延迟加载（首次使用时）
    - 所有 GOP 共享同一模型实例
    - 线程锁保护模型访问
    """

    _instance: Optional['SemanticExtractor'] = None
    _lock = threading.Lock()
    _model: Optional[YOLO] = None
    _model_lock = threading.Lock()

    def __init__(self, model_path: str = "yolov8n.pt", confidence: float = 0.5):
        """
        初始化语义提取器

        Args:
            model_path: YOLO 模型路径（默认 yolov8n.pt）
            confidence: 检测置信度阈值（默认 0.5）
        """
        self.model_path = model_path
        self.confidence = confidence
        logger.info(f"语义提取器初始化: model={model_path}, confidence={confidence}")

    @classmethod
    def get_instance(cls) -> 'SemanticExtractor':
        """
        获取单例实例（线程安全）

        Returns:
            SemanticExtractor 单例实例
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(
                        model_path=SETTINGS.semantic_model_path,
                        confidence=SETTINGS.semantic_confidence
                    )
        return cls._instance

    def _load_model(self) -> YOLO:
        """
        延迟加载 YOLO 模型（线程安全）

        Returns:
            YOLO 模型实例

        Raises:
            Exception: 模型加载失败
        """
        if self._model is None:
            with self._model_lock:
                if self._model is None:
                    logger.info(f"加载 YOLO 模型: {self.model_path}")
                    self._model = YOLO(self.model_path)
                    logger.info("YOLO 模型加载成功")
        return self._model

    def extract(
        self,
        keyframe_frame: np.ndarray,
        gop_id: int,
        start_time: float
    ) -> Optional[SemanticFingerprint]:
        """
        从 GOP 关键帧提取语义指纹

        Args:
            keyframe_frame: 关键帧图像（BGR numpy 数组）
            gop_id: GOP 标识符
            start_time: GOP 开始时间（秒）

        Returns:
            SemanticFingerprint 对象，失败时返回 None
        """
        try:
            # 验证输入
            if keyframe_frame is None or keyframe_frame.size == 0:
                logger.warning(f"GOP {gop_id}: 关键帧为空")
                return None

            if len(keyframe_frame.shape) != 3:
                logger.warning(f"GOP {gop_id}: 关键帧维度无效 {keyframe_frame.shape}")
                return None

            # 加载模型
            model = self._load_model()

            # 运行 YOLO 推理（线程安全）
            with self._model_lock:
                results = model.predict(
                    keyframe_frame,
                    conf=self.confidence,
                    verbose=False
                )

            # 统计对象计数
            objects: Dict[str, int] = {}
            if results and len(results) > 0:
                result = results[0]
                if result.boxes is not None and len(result.boxes) > 0:
                    for box in result.boxes:
                        cls_id = int(box.cls[0])
                        class_name = model.names[cls_id]
                        objects[class_name] = objects.get(class_name, 0) + 1

            total_count = sum(objects.values())

            # 生成 ISO 8601 时间戳
            timestamp = datetime.fromtimestamp(start_time, tz=timezone.utc).isoformat()

            # 构建确定性 JSON
            data = {
                "gop_id": gop_id,
                "timestamp": timestamp,
                "objects": objects,
                "total_count": total_count
            }

            # 确定性序列化（键排序，无空格）
            json_str = json.dumps(data, sort_keys=True, separators=(',', ':'))

            # 计算语义哈希
            semantic_hash = hashlib.sha256(json_str.encode('utf-8')).hexdigest()

            logger.debug(
                f"GOP {gop_id} 语义提取成功: {total_count} 个对象 "
                f"({', '.join(f'{k}:{v}' for k, v in objects.items()) if objects else '无'})"
            )

            return SemanticFingerprint(
                gop_id=gop_id,
                timestamp=timestamp,
                objects=objects,
                total_count=total_count,
                json_str=json_str,
                semantic_hash=semantic_hash
            )

        except Exception as e:
            logger.warning(f"GOP {gop_id} 语义提取失败: {e}")
            return None
