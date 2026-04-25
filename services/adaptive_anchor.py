"""
自适应锚点模块 - 基于事件重要性评分 (EIS) 动态调整上报频率

该模块根据场景活跃度自动调整 SegmentRoot 上报间隔：
- 低活跃度（EIS < 0.3）：每 5 分钟上报一次
- 中活跃度（0.3 ≤ EIS ≤ 0.7）：每 1 分钟上报一次
- 高活跃度（EIS > 0.7）：每 10 秒上报一次

支持两种 EIS 模式（通过环境变量 EIS_MODE 切换）：
- lite（默认）：纯 YOLO 目标计数
- full：光流运动分析 + 统计异常检测 + 规则引擎加权融合

设计特点：
- 5 GOP 滑动窗口均值平滑（响应更灵敏）
- 状态切换防抖（快升慢降）
- 边缘设备友好（光流缩放至 320×240，无重依赖）
"""

import logging
import math
import os
import time
from collections import deque
from dataclasses import dataclass, field
from statistics import mean
from typing import Dict, List, Optional

import cv2
import numpy as np

from services.semantic_fingerprint import SemanticFingerprint

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class MotionFeatures:
    """
    光流运动特征

    - magnitude_mean: 光流幅值均值（整体运动强度）
    - magnitude_max: 光流幅值最大值（最剧烈运动区域）
    - magnitude_std: 光流幅值标准差（运动分布均匀性）
    - motion_area_ratio: 运动区域占比（幅值 > 阈值的像素比例）
    - dominant_direction: 主运动方向角度（0-360°）
    """
    magnitude_mean: float = 0.0
    magnitude_max: float = 0.0
    magnitude_std: float = 0.0
    motion_area_ratio: float = 0.0
    dominant_direction: float = 0.0


@dataclass
class AnomalyResult:
    """
    异常检测结果

    - anomaly_score: 0.0~1.0 归一化异常分数
    - is_anomaly: 是否超过阈值
    - z_scores: 各维度的 z-score（供调试）
    """
    anomaly_score: float = 0.0
    is_anomaly: bool = False
    z_scores: list = field(default_factory=list)


@dataclass
class AnchorDecision:
    """
    锚点决策数据结构

    包含 EIS 评分、平滑计数、活跃等级和上报决策：
    - eis_score: 事件重要性评分 (0.0~1.0)
    - smoothed_count: 滑动窗口平均目标数
    - level: 活跃等级 ("LOW", "MEDIUM", "HIGH")
    - report_interval_seconds: 上报间隔 (300, 60, 10)
    - should_report_now: 是否应立即上报
    - motion_features: 光流运动特征（仅 full 模式）
    - anomaly_result: 异常检测结果（仅 full 模式）
    - signal_breakdown: 各信号分量（仅 full 模式）
    """
    eis_score: float
    smoothed_count: float
    level: str
    report_interval_seconds: int
    should_report_now: bool
    motion_features: Optional[MotionFeatures] = None
    anomaly_result: Optional[AnomalyResult] = None
    signal_breakdown: Optional[dict] = None
    mab_arm: Optional[int] = None


# ---------------------------------------------------------------------------
# OpticalFlowAnalyzer
# ---------------------------------------------------------------------------

# Farneback 计算参数
_FLOW_RESIZE = (320, 240)
_FLOW_PYR_SCALE = 0.5
_FLOW_LEVELS = 3
_FLOW_WINSIZE = 15
_FLOW_ITERATIONS = 3
_FLOW_POLY_N = 5
_FLOW_POLY_SIGMA = 1.2
_MOTION_THRESHOLD = 2.0  # 像素位移 > 2 视为运动


class OpticalFlowAnalyzer:
    """
    光流运动分析器

    使用 Farneback 稠密光流计算相邻 GOP 关键帧之间的运动强度。
    帧在计算前缩放至 320×240 以降低 CPU 开销。
    """

    def __init__(self):
        self._prev_gray: Optional[np.ndarray] = None

    def _to_gray_resized(self, frame: np.ndarray) -> np.ndarray:
        """将 BGR 帧缩放至 _FLOW_RESIZE 并转灰度。"""
        resized = cv2.resize(frame, _FLOW_RESIZE, interpolation=cv2.INTER_AREA)
        return cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

    def analyze(self, frame: np.ndarray) -> MotionFeatures:
        """
        计算当前帧与上一帧之间的光流运动特征。

        Args:
            frame: BGR numpy 数组（关键帧）

        Returns:
            MotionFeatures 实例（首帧返回全零）
        """
        gray = self._to_gray_resized(frame)

        if self._prev_gray is None:
            self._prev_gray = gray
            return MotionFeatures()

        # 计算 Farneback 稠密光流
        flow = cv2.calcOpticalFlowFarneback(
            self._prev_gray, gray, None,
            pyr_scale=_FLOW_PYR_SCALE,
            levels=_FLOW_LEVELS,
            winsize=_FLOW_WINSIZE,
            iterations=_FLOW_ITERATIONS,
            poly_n=_FLOW_POLY_N,
            poly_sigma=_FLOW_POLY_SIGMA,
            flags=0,
        )

        self._prev_gray = gray

        # 转换为极坐标（幅值 + 角度）
        mag, ang = cv2.cartToPolar(flow[..., 0], flow[..., 1], angleInDegrees=True)

        magnitude_mean = float(np.mean(mag))
        magnitude_max = float(np.max(mag))
        magnitude_std = float(np.std(mag))

        # 运动区域占比
        motion_pixels = np.sum(mag > _MOTION_THRESHOLD)
        total_pixels = mag.size
        motion_area_ratio = float(motion_pixels / total_pixels) if total_pixels > 0 else 0.0

        # 主运动方向：对运动区域的角度加权平均
        if motion_pixels > 0:
            mask = mag > _MOTION_THRESHOLD
            # 用幅值加权的角度均值
            weights = mag[mask]
            angles = ang[mask]
            # 处理角度环绕：转为单位向量后求均值
            rad = np.deg2rad(angles)
            mean_sin = float(np.average(np.sin(rad), weights=weights))
            mean_cos = float(np.average(np.cos(rad), weights=weights))
            dominant_direction = float(np.rad2deg(math.atan2(mean_sin, mean_cos))) % 360.0
        else:
            dominant_direction = 0.0

        return MotionFeatures(
            magnitude_mean=magnitude_mean,
            magnitude_max=magnitude_max,
            magnitude_std=magnitude_std,
            motion_area_ratio=motion_area_ratio,
            dominant_direction=dominant_direction,
        )


# ---------------------------------------------------------------------------
# AnomalyDetector
# ---------------------------------------------------------------------------

_ANOMALY_COLD_START = 10  # 冷启动期样本数


class AnomalyDetector:
    """
    滑动窗口统计异常检测

    维护最近 history_size 个特征向量，计算各维度 z-score，
    取最大 z-score 作为异常指标。冷启动期（< 10 样本）不报异常。
    """

    def __init__(self, history_size: int = 100, z_threshold: float = 2.5):
        self.history_size = history_size
        self.z_threshold = z_threshold
        self._history: deque = deque(maxlen=history_size)

    def update(self, features: np.ndarray) -> AnomalyResult:
        """
        更新历史并检测异常。

        Args:
            features: 1D 向量 [total_count, magnitude_mean, magnitude_max, motion_area_ratio]

        Returns:
            AnomalyResult
        """
        features = np.asarray(features, dtype=np.float64)

        # 冷启动期
        if len(self._history) < _ANOMALY_COLD_START:
            self._history.append(features.copy())
            return AnomalyResult(anomaly_score=0.0, is_anomaly=False, z_scores=[0.0] * len(features))

        # 计算历史统计量
        history_array = np.array(self._history)  # shape: (N, D)
        means = np.mean(history_array, axis=0)
        stds = np.std(history_array, axis=0)

        # z-score
        z_scores = np.abs(features - means) / (stds + 1e-8)
        z_scores_list = z_scores.tolist()

        raw_score = float(np.max(z_scores))
        anomaly_score = min(1.0, raw_score / (2.0 * self.z_threshold))
        is_anomaly = raw_score > self.z_threshold

        # 将当前特征加入历史
        self._history.append(features.copy())

        return AnomalyResult(
            anomaly_score=anomaly_score,
            is_anomaly=is_anomaly,
            z_scores=z_scores_list,
        )


# ---------------------------------------------------------------------------
# EISRuleEngine
# ---------------------------------------------------------------------------

_DEFAULT_WEIGHTS = {"object_count": 0.35, "motion": 0.35, "anomaly": 0.30}


class EISRuleEngine:
    """
    EIS 规则引擎 — 将多信号融合为最终 EIS 分数

    加权融合三个信号源 + 规则覆盖：
    - 目标计数信号（4 级 + person 奖励）
    - 运动信号（4 级 + 整体移动覆盖）
    - 异常信号（直通 anomaly_score）
    """

    def __init__(self, weights: Optional[Dict[str, float]] = None):
        self.weights = weights or dict(_DEFAULT_WEIGHTS)

    def compute_eis(
        self,
        semantic: SemanticFingerprint,
        motion: MotionFeatures,
        anomaly: AnomalyResult,
    ) -> tuple:
        """
        计算融合 EIS 分数。

        Returns:
            (eis_score, signal_breakdown) — eis_score ∈ [0, 1]
        """
        # --- 目标计数信号 ---
        tc = semantic.total_count
        if tc == 0:
            object_signal = 0.1
        elif tc <= 3:
            object_signal = 0.3
        elif tc <= 8:
            object_signal = 0.6
        else:
            object_signal = 0.9

        # person 奖励
        person_count = semantic.objects.get("person", 0)
        if person_count >= 3:
            object_signal = min(1.0, object_signal + 0.1)

        # --- 运动信号 ---
        mm = motion.magnitude_mean
        if mm < 1.0:
            motion_signal = 0.1
        elif mm < 5.0:
            motion_signal = 0.4
        elif mm < 15.0:
            motion_signal = 0.7
        else:
            motion_signal = 0.95

        if motion.motion_area_ratio > 0.8:
            motion_signal = 0.95

        # --- 异常信号 ---
        anomaly_signal = anomaly.anomaly_score

        # --- 加权融合 ---
        w_obj = self.weights["object_count"]
        w_mot = self.weights["motion"]
        w_ano = self.weights["anomaly"]
        eis = w_obj * object_signal + w_mot * motion_signal + w_ano * anomaly_signal

        # --- 规则覆盖 ---
        if anomaly.is_anomaly:
            eis = max(eis, 0.8)

        if motion.motion_area_ratio > 0.9 and motion.magnitude_mean > 20:
            eis = 0.95

        eis = max(0.0, min(1.0, eis))

        breakdown = {
            "object": round(object_signal, 4),
            "motion": round(motion_signal, 4),
            "anomaly": round(anomaly_signal, 4),
        }

        return eis, breakdown


# ---------------------------------------------------------------------------
# AdaptiveAnchor
# ---------------------------------------------------------------------------


class AdaptiveAnchor:
    """
    自适应锚点管理器

    根据场景活跃度动态调整上报频率：
    - 使用 5 GOP 滑动窗口平均数平滑目标计数
    - 快速升级（3 次确认）、缓慢降级（5 次确认）
    - 三级上报间隔：300s / 60s / 10s

    通过 eis_mode 切换 lite/full 两种 EIS 计算模式。
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
        window_size: int = 5,
        upgrade_confirm: int = 3,
        downgrade_confirm: int = 5,
        eis_mode: Optional[str] = None,
        anchor_mode: Optional[str] = None,
    ):
        """
        初始化自适应锚点管理器

        Args:
            window_size: 滑动窗口大小（默认 5）
            upgrade_confirm: 升级所需确认次数（默认 3）
            downgrade_confirm: 降级所需确认次数（默认 5）
            eis_mode: EIS 模式 ("lite" 或 "full")，默认读取环境变量 EIS_MODE
            anchor_mode: 锚定策略 ("fixed"/"mab_ucb"/"mab_thompson")，默认读取 ANCHOR_MODE
        """
        self.window_size = window_size
        self.upgrade_confirm = upgrade_confirm
        self.downgrade_confirm = downgrade_confirm

        # EIS 模式
        self.eis_mode = eis_mode or os.environ.get("EIS_MODE", "lite")

        # 锚定模式
        self.anchor_mode = anchor_mode or os.environ.get("ANCHOR_MODE", "fixed")

        # 滑动窗口
        self._count_history: deque[int] = deque(maxlen=window_size)

        # EIS 分数滑动窗口（用于平滑 full 模式的连续 EIS）
        self._eis_history: deque[float] = deque(maxlen=window_size)
        self._latest_eis: float = 0.0

        # 状态管理
        self._current_level = "LOW"
        self._pending_level: Optional[str] = None
        self._confirm_counter = 0

        # 上报时间跟踪
        self._last_report_time = 0.0  # Initialize to 0 so first report is always True

        # Full 模式组件
        self._flow_analyzer: Optional[OpticalFlowAnalyzer] = None
        self._anomaly_detector: Optional[AnomalyDetector] = None
        self._rule_engine: Optional[EISRuleEngine] = None

        if self.eis_mode == "full":
            self._flow_analyzer = OpticalFlowAnalyzer()
            self._anomaly_detector = AnomalyDetector()
            self._rule_engine = EISRuleEngine()

        # MAB 锚定管理器
        self._mab_manager = None
        self._gop_counter = 0
        if self.anchor_mode in ("mab_ucb", "mab_thompson"):
            from services.mab_anchor import MABAnchorManager
            self._mab_manager = MABAnchorManager(mode=self.anchor_mode)

        logger.info(
            f"自适应锚点初始化: window_size={window_size}, "
            f"upgrade_confirm={upgrade_confirm}, downgrade_confirm={downgrade_confirm}, "
            f"eis_mode={self.eis_mode}, anchor_mode={self.anchor_mode}"
        )

    def _calculate_eis(self, smoothed_count: float) -> float:
        """
        计算事件重要性评分 (EIS) — lite 模式

        Args:
            smoothed_count: 5 GOP 窗口平均目标数

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

    def update(
        self,
        semantic: SemanticFingerprint,
        keyframe: Optional[np.ndarray] = None,
    ) -> AnchorDecision:
        """
        更新自适应锚点状态并返回决策

        Args:
            semantic: 语义指纹对象
            keyframe: GOP 关键帧 BGR 图像（仅 full 模式使用）

        Returns:
            AnchorDecision 对象
        """
        motion_features = None
        anomaly_result = None
        signal_breakdown = None

        if self.eis_mode == "full" and keyframe is not None:
            # --- Full EIS 模式 ---
            # 1. 光流分析
            motion_features = self._flow_analyzer.analyze(keyframe)

            # 2. 构造特征向量 → 异常检测
            feature_vec = np.array([
                semantic.total_count,
                motion_features.magnitude_mean,
                motion_features.magnitude_max,
                motion_features.motion_area_ratio,
            ], dtype=np.float64)
            anomaly_result = self._anomaly_detector.update(feature_vec)

            # 3. 规则引擎融合
            eis_score, signal_breakdown = self._rule_engine.compute_eis(
                semantic, motion_features, anomaly_result,
            )

            # 4. 滑动窗口均值平滑 EIS
            self._eis_history.append(eis_score)
            smoothed_eis = float(mean(self._eis_history))

            # 5. 也维护 count 历史（用于 smoothed_count 字段兼容）
            self._count_history.append(semantic.total_count)
            smoothed_count = float(mean(self._count_history))

            # 6. 确定目标等级并防抖
            target_level = self._eis_to_level(smoothed_eis)
            self._update_level(target_level)

            # 使用平滑后的 EIS
            final_eis = smoothed_eis
        else:
            # --- Lite EIS 模式 ---
            # 1. 添加到滑动窗口
            self._count_history.append(semantic.total_count)

            # 2. 计算 5 GOP 窗口平均目标数
            smoothed_count = float(mean(self._count_history))

            # 3. 计算 EIS 评分
            final_eis = self._calculate_eis(smoothed_count)

            # 4. 确定目标等级
            target_level = self._eis_to_level(final_eis)

            # 5. 更新等级（带防抖）
            self._update_level(target_level)

            # 6. Lite 模式也维护 EIS 历史，供前端仪表盘显示
            self._eis_history.append(final_eis)

        # --- 公共部分 ---
        self._latest_eis = final_eis

        # 获取上报间隔
        report_interval = self._level_to_interval(self._current_level)

        # 判断是否应立即上报
        mab_arm = None
        if self._mab_manager is not None:
            # MAB 模式：由 MAB 策略决定是否锚定
            self._gop_counter += 1
            should_report_now = self._mab_manager.should_anchor(self._gop_counter)
            mab_arm = self._mab_manager.current_arm
        else:
            # Fixed 模式：基于时间间隔决定
            current_time = time.time()
            time_since_last_report = current_time - self._last_report_time
            should_report_now = time_since_last_report >= report_interval

        # 如果需要上报，更新上报时间
        if should_report_now:
            self._last_report_time = time.time()
            logger.debug(
                f"GOP {semantic.gop_id}: 触发上报 "
                f"(level={self._current_level}, interval={report_interval}s, "
                f"anchor_mode={self.anchor_mode})"
            )

        return AnchorDecision(
            eis_score=final_eis,
            smoothed_count=smoothed_count,
            level=self._current_level,
            report_interval_seconds=report_interval,
            should_report_now=should_report_now,
            motion_features=motion_features,
            anomaly_result=anomaly_result,
            signal_breakdown=signal_breakdown,
            mab_arm=mab_arm,
        )

    def report_anchor_result(
        self,
        success: bool,
        cost: float = 0.0,
        latency: float = 0.0,
    ) -> None:
        """
        报告锚定结果（仅 MAB 模式使用）。

        Args:
            success: 锚定/验证是否成功
            cost: 锚定成本
            latency: 锚定延迟（秒）
        """
        if self._mab_manager is not None:
            self._mab_manager.report_result(success, cost, latency)
