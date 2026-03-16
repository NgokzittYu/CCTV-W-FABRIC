"""
自适应锚点模块 - 基于事件重要性评分 (EIS) 动态调整上报频率

该模块根据场景活跃度自动调整 SegmentRoot 上报间隔：
- 低活跃度（EIS < 0.3）：每 5 分钟上报一次
- 中活跃度（0.3 ≤ EIS ≤ 0.7）：每 1 分钟上报一次
- 高活跃度（EIS > 0.7）：每 10 秒上报一次

设计特点：
- 滑动窗口中位数平滑（抗异常值）
- 状态切换防抖（快升慢降）
- 基于 YOLO 目标计数的 EIS 计算
"""

import logging
import time
from collections import deque
from dataclasses import dataclass
from statistics import median
from typing import Optional

from services.semantic_fingerprint import SemanticFingerprint

logger = logging.getLogger(__name__)


@dataclass
class AnchorDecision:
    """
    锚点决策数据结构

    包含 EIS 评分、平滑计数、活跃等级和上报决策：
    - eis_score: 事件重要性评分 (0.1, 0.5, 0.9)
    - smoothed_count: 滑动窗口中位数
    - level: 活跃等级 ("LOW", "MEDIUM", "HIGH")
    - report_interval_seconds: 上报间隔 (300, 60, 10)
    - should_report_now: 是否应立即上报
    """
    eis_score: float
    smoothed_count: int
    level: str
    report_interval_seconds: int
    should_report_now: bool


class AdaptiveAnchor:
    """
    自适应锚点管理器

    根据场景活跃度动态调整上报频率：
    - 使用滑动窗口中位数平滑目标计数
    - 快速升级（3 次确认）、缓慢降级（5 次确认）
    - 三级上报间隔：300s / 60s / 10s
    """

    # EIS 等级阈值
    LOW_THRESHOLD = 0.3
    HIGH_THRESHOLD = 0.7

    # 上报间隔（秒）
    INTERVAL_LOW = 300      # 5 分钟
    INTERVAL_MEDIUM = 60    # 1 分钟
    INTERVAL_HIGH = 10      # 10 秒

    def __init__(
        self,
        window_size: int = 10,
        upgrade_confirm: int = 3,
        downgrade_confirm: int = 5
    ):
        """
        初始化自适应锚点管理器

        Args:
            window_size: 滑动窗口大小（默认 10）
            upgrade_confirm: 升级所需确认次数（默认 3）
            downgrade_confirm: 降级所需确认次数（默认 5）
        """
        self.window_size = window_size
        self.upgrade_confirm = upgrade_confirm
        self.downgrade_confirm = downgrade_confirm

        # 滑动窗口
        self._count_history: deque[int] = deque(maxlen=window_size)

        # 状态管理
        self._current_level = "LOW"
        self._pending_level: Optional[str] = None
        self._confirm_counter = 0

        # 上报时间跟踪
        self._last_report_time = 0.0  # Initialize to 0 so first report is always True

        logger.info(
            f"自适应锚点初始化: window_size={window_size}, "
            f"upgrade_confirm={upgrade_confirm}, downgrade_confirm={downgrade_confirm}"
        )

    def _calculate_eis(self, smoothed_count: int) -> float:
        """
        计算事件重要性评分 (EIS)

        Args:
            smoothed_count: 平滑后的目标计数

        Returns:
            EIS 评分 (0.1, 0.5, 0.9)
        """
        if smoothed_count == 0:
            return 0.1
        elif smoothed_count <= 5:
            return 0.5
        else:
            return 0.9

    def _eis_to_level(self, eis: float) -> str:
        """
        将 EIS 评分转换为活跃等级

        Args:
            eis: EIS 评分

        Returns:
            活跃等级 ("LOW", "MEDIUM", "HIGH")
        """
        if eis < self.LOW_THRESHOLD:
            return "LOW"
        elif eis <= self.HIGH_THRESHOLD:
            return "MEDIUM"
        else:
            return "HIGH"

    def _level_to_interval(self, level: str) -> int:
        """
        将活跃等级转换为上报间隔

        Args:
            level: 活跃等级

        Returns:
            上报间隔（秒）
        """
        if level == "LOW":
            return self.INTERVAL_LOW
        elif level == "MEDIUM":
            return self.INTERVAL_MEDIUM
        else:
            return self.INTERVAL_HIGH

    def _update_level(self, target_level: str) -> None:
        """
        更新活跃等级（带防抖逻辑）

        Args:
            target_level: 目标等级
        """
        # 如果目标等级与当前等级相同，重置待定状态
        if target_level == self._current_level:
            self._pending_level = None
            self._confirm_counter = 0
            return

        # 如果目标等级与待定等级不同，重置计数器
        if target_level != self._pending_level:
            self._pending_level = target_level
            self._confirm_counter = 1
            logger.debug(f"等级切换待定: {self._current_level} → {target_level} (1)")
            return

        # 累加确认计数
        self._confirm_counter += 1

        # 判断是升级还是降级
        level_order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
        is_upgrade = level_order[target_level] > level_order[self._current_level]

        # 确定所需确认次数
        required_confirms = self.upgrade_confirm if is_upgrade else self.downgrade_confirm

        # 检查是否达到确认次数
        if self._confirm_counter >= required_confirms:
            old_level = self._current_level
            self._current_level = target_level
            self._pending_level = None
            self._confirm_counter = 0
            self._last_report_time = 0.0  # Reset timer to trigger immediate report
            logger.info(
                f"等级切换完成: {old_level} → {self._current_level} "
                f"({'升级' if is_upgrade else '降级'})"
            )
        else:
            logger.debug(
                f"等级切换待定: {self._current_level} → {target_level} "
                f"({self._confirm_counter}/{required_confirms})"
            )

    def update(self, semantic: SemanticFingerprint) -> AnchorDecision:
        """
        更新自适应锚点状态并返回决策

        Args:
            semantic: 语义指纹对象

        Returns:
            AnchorDecision 对象
        """
        # 1. 添加到滑动窗口
        self._count_history.append(semantic.total_count)

        # 2. 计算平滑计数（中位数）
        smoothed_count = int(median(self._count_history))

        # 3. 计算 EIS 评分
        eis_score = self._calculate_eis(smoothed_count)

        # 4. 确定目标等级
        target_level = self._eis_to_level(eis_score)

        # 5. 更新等级（带防抖）
        self._update_level(target_level)

        # 6. 获取上报间隔
        report_interval = self._level_to_interval(self._current_level)

        # 7. 判断是否应立即上报
        current_time = time.time()
        time_since_last_report = current_time - self._last_report_time
        should_report_now = time_since_last_report >= report_interval

        # 8. 如果需要上报，更新上报时间
        if should_report_now:
            self._last_report_time = current_time
            logger.debug(
                f"GOP {semantic.gop_id}: 触发上报 "
                f"(level={self._current_level}, interval={report_interval}s, "
                f"elapsed={time_since_last_report:.1f}s)"
            )

        return AnchorDecision(
            eis_score=eis_score,
            smoothed_count=smoothed_count,
            level=self._current_level,
            report_interval_seconds=report_interval,
            should_report_now=should_report_now
        )
