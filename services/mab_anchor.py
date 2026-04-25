"""
MAB (Multi-Armed Bandit) 自适应锚定策略

根据实时反馈（验证成功率、锚定成本、延迟）动态学习最优锚定间隔，
替代现有固定阈值分档策略。

锚定臂定义：
- Arm 0: 每 1 个 GOP 锚定一次（最激进）
- Arm 1: 每 2 个 GOP 锚定一次
- Arm 2: 每 5 个 GOP 锚定一次
- Arm 3: 每 10 个 GOP 锚定一次（最保守）

通过 ANCHOR_MODE 环境变量控制：
- fixed（默认）：使用现有 EIS 固定阈值策略
- mab_ucb：UCB1 策略
- mab_thompson：Thompson Sampling 策略
"""

import json
import logging
import math
import os
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ── 臂定义 ────────────────────────────────────────────────────────────

ARM_INTERVALS = [1, 2, 5, 10]  # 每 N 个 GOP 锚定一次
NUM_ARMS = len(ARM_INTERVALS)

# ── Reward 权重 ───────────────────────────────────────────────────────

_REWARD_ALPHA = 0.6   # 验证成功率权重
_REWARD_BETA = 0.2    # 锚定成本惩罚权重
_REWARD_GAMMA = 0.2   # 延迟惩罚权重

# 成本和延迟的归一化参考值
_COST_REF = 1.0       # 参考成本（归一化用）
_LATENCY_REF = 5.0    # 参考延迟（秒，归一化用）


def compute_reward(success: bool, cost: float = 0.0, latency: float = 0.0) -> float:
    """
    计算单次锚定的 reward 值。

    reward = α * success_rate - β * normalized_cost - γ * normalized_latency

    Args:
        success: 验证是否成功
        cost: 锚定成本（归一化到 [0, 1]）
        latency: 锚定延迟（秒）

    Returns:
        reward ∈ [-1, 1]
    """
    success_val = 1.0 if success else 0.0
    norm_cost = min(1.0, cost / _COST_REF) if _COST_REF > 0 else 0.0
    norm_latency = min(1.0, latency / _LATENCY_REF) if _LATENCY_REF > 0 else 0.0

    reward = _REWARD_ALPHA * success_val - _REWARD_BETA * norm_cost - _REWARD_GAMMA * norm_latency
    return max(-1.0, min(1.0, reward))


def estimate_resource_savings(interval: int) -> float:
    """Estimate anchoring write reduction versus anchoring every GOP.

    The metric is intentionally limited to expected chain-write count reduction:
    interval=1 means no savings, interval=5 means one write per five GOPs and
    therefore an estimated 80% reduction.
    """
    if interval <= 1:
        return 0.0
    return round((1.0 - (1.0 / interval)) * 100.0, 4)


# ── 策略基类 ──────────────────────────────────────────────────────────

class BanditStrategy(ABC):
    """MAB 策略抽象基类。"""

    @abstractmethod
    def select_arm(self) -> int:
        """选择一个臂。"""

    @abstractmethod
    def update(self, arm: int, reward: float) -> None:
        """更新臂的统计信息。"""

    @abstractmethod
    def to_dict(self) -> dict:
        """序列化为字典。"""

    @classmethod
    @abstractmethod
    def from_dict(cls, data: dict) -> "BanditStrategy":
        """从字典反序列化。"""


# ── UCB1 策略 ─────────────────────────────────────────────────────────

class UCBStrategy(BanditStrategy):
    """
    UCB1 (Upper Confidence Bound) 策略。

    选择公式：argmax_i [ Q(i) + c * sqrt(ln(N) / n(i)) ]
    - Q(i): 臂 i 的平均 reward
    - N: 总拉臂次数
    - n(i): 臂 i 被拉的次数
    - c: 探索系数（默认 sqrt(2)）
    """

    def __init__(self, n_arms: int = NUM_ARMS, exploration_coeff: float = 1.414):
        self.n_arms = n_arms
        self.exploration_coeff = exploration_coeff
        self.counts: List[int] = [0] * n_arms       # 每个臂被拉的次数
        self.values: List[float] = [0.0] * n_arms   # 每个臂的累计 reward
        self.total_count: int = 0

    def select_arm(self) -> int:
        # 确保每个臂至少被拉一次
        for i in range(self.n_arms):
            if self.counts[i] == 0:
                return i

        ucb_values = []
        for i in range(self.n_arms):
            avg_reward = self.values[i] / self.counts[i]
            exploration = self.exploration_coeff * math.sqrt(
                math.log(self.total_count) / self.counts[i]
            )
            ucb_values.append(avg_reward + exploration)

        return int(np.argmax(ucb_values))

    def update(self, arm: int, reward: float) -> None:
        self.counts[arm] += 1
        self.values[arm] += reward
        self.total_count += 1

    def get_arm_stats(self) -> List[dict]:
        """获取每个臂的统计信息。"""
        stats = []
        for i in range(self.n_arms):
            avg = self.values[i] / self.counts[i] if self.counts[i] > 0 else 0.0
            stats.append({
                "arm": i,
                "interval": ARM_INTERVALS[i],
                "count": self.counts[i],
                "avg_reward": round(avg, 4),
                "total_reward": round(self.values[i], 4),
            })
        return stats

    def to_dict(self) -> dict:
        return {
            "type": "ucb",
            "n_arms": self.n_arms,
            "exploration_coeff": self.exploration_coeff,
            "counts": self.counts,
            "values": self.values,
            "total_count": self.total_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "UCBStrategy":
        obj = cls(n_arms=data["n_arms"], exploration_coeff=data["exploration_coeff"])
        obj.counts = data["counts"]
        obj.values = data["values"]
        obj.total_count = data["total_count"]
        return obj


# ── Thompson Sampling 策略 ────────────────────────────────────────────

class ThompsonStrategy(BanditStrategy):
    """
    Thompson Sampling 策略。

    每个臂维护一个 Beta(α, β) 分布：
    - 成功（reward > 0）→ α += 1
    - 失败（reward ≤ 0）→ β += 1
    选择时从各臂的 Beta 分布采样，选择样本值最大的臂。
    """

    def __init__(self, n_arms: int = NUM_ARMS):
        self.n_arms = n_arms
        self.alphas: List[float] = [1.0] * n_arms   # Beta 先验 α
        self.betas: List[float] = [1.0] * n_arms    # Beta 先验 β

    def select_arm(self) -> int:
        samples = [
            np.random.beta(self.alphas[i], self.betas[i])
            for i in range(self.n_arms)
        ]
        return int(np.argmax(samples))

    def update(self, arm: int, reward: float) -> None:
        if reward > 0:
            self.alphas[arm] += 1.0
        else:
            self.betas[arm] += 1.0

    def get_arm_stats(self) -> List[dict]:
        """获取每个臂的统计信息。"""
        stats = []
        for i in range(self.n_arms):
            total = self.alphas[i] + self.betas[i] - 2.0  # 减去先验
            success_rate = (self.alphas[i] - 1.0) / total if total > 0 else 0.0
            stats.append({
                "arm": i,
                "interval": ARM_INTERVALS[i],
                "alpha": self.alphas[i],
                "beta": self.betas[i],
                "success_rate": round(success_rate, 4),
            })
        return stats

    def to_dict(self) -> dict:
        return {
            "type": "thompson",
            "n_arms": self.n_arms,
            "alphas": self.alphas,
            "betas": self.betas,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ThompsonStrategy":
        obj = cls(n_arms=data["n_arms"])
        obj.alphas = data["alphas"]
        obj.betas = data["betas"]
        return obj


# ── MABAnchorManager ──────────────────────────────────────────────────

_DEFAULT_STATE_PATH = "data/mab_state.json"


class MABAnchorManager:
    """
    MAB 锚定管理器。

    根据 MAB 策略动态决定是否锚定当前 GOP。

    Usage::

        manager = MABAnchorManager(mode="mab_ucb")

        for gop_index in range(100):
            if manager.should_anchor(gop_index):
                # 执行锚定
                success = True
                manager.report_result(success, cost=0.1, latency=0.5)

        manager.save_state()
    """

    def __init__(
        self,
        mode: str = "mab_ucb",
        state_path: Optional[str] = None,
        auto_load: bool = True,
    ):
        """
        Args:
            mode: 策略模式 ("mab_ucb" 或 "mab_thompson")
            state_path: 状态持久化路径
            auto_load: 是否自动尝试加载已有状态
        """
        self.mode = mode
        self.state_path = state_path or _DEFAULT_STATE_PATH
        self._lock = threading.Lock()

        # 创建策略
        if mode == "mab_thompson":
            self._strategy: BanditStrategy = ThompsonStrategy()
        else:
            self._strategy: BanditStrategy = UCBStrategy()

        # 当前选择的臂和 GOP 计数
        self._current_arm: int = 0
        self._gop_since_last_anchor: int = 0
        self._total_decisions: int = 0
        self._anchor_count: int = 0

        # 自动加载
        if auto_load:
            self.load_state()

        # 选择初始臂
        self._current_arm = self._strategy.select_arm()

        logger.info(
            "MABAnchorManager initialized: mode=%s, initial_arm=%d (interval=%d)",
            mode, self._current_arm, ARM_INTERVALS[self._current_arm],
        )

    @property
    def current_arm(self) -> int:
        return self._current_arm

    @property
    def current_interval(self) -> int:
        return ARM_INTERVALS[self._current_arm]

    def should_anchor(self, gop_index: int) -> bool:
        """
        判断当前 GOP 是否应该锚定。

        基于当前臂的间隔（每 N 个 GOP 锚定一次）。

        Args:
            gop_index: 当前 GOP 索引（全局）

        Returns:
            True 表示应该锚定
        """
        with self._lock:
            self._gop_since_last_anchor += 1
            self._total_decisions += 1

            interval = ARM_INTERVALS[self._current_arm]
            if self._gop_since_last_anchor >= interval:
                self._gop_since_last_anchor = 0
                self._anchor_count += 1
                return True
            return False

    def report_result(
        self,
        success: bool,
        cost: float = 0.0,
        latency: float = 0.0,
    ) -> None:
        """
        报告锚定结果，更新 MAB 策略。

        应在每次锚定完成后调用。

        Args:
            success: 锚定/验证是否成功
            cost: 锚定成本
            latency: 锚定延迟（秒）
        """
        with self._lock:
            reward = compute_reward(success, cost, latency)
            self._strategy.update(self._current_arm, reward)

            # 选择下一个臂
            self._current_arm = self._strategy.select_arm()

            logger.debug(
                "MAB update: reward=%.3f, next_arm=%d (interval=%d)",
                reward, self._current_arm, ARM_INTERVALS[self._current_arm],
            )

    def get_stats(self) -> dict:
        """获取 MAB 统计信息。"""
        actual_anchor_rate = (
            (self._anchor_count / self._total_decisions) * 100.0
            if self._total_decisions > 0
            else 0.0
        )
        actual_resource_savings = (
            max(0.0, 100.0 - actual_anchor_rate)
            if self._total_decisions > 0
            else 0.0
        )
        return {
            "mode": self.mode,
            "current_arm": self._current_arm,
            "current_interval": self.current_interval,
            "total_decisions": self._total_decisions,
            "anchor_count": self._anchor_count,
            "estimated_resource_savings_percent": estimate_resource_savings(self.current_interval),
            "actual_anchor_rate_percent": round(actual_anchor_rate, 4),
            "actual_resource_savings_percent": round(actual_resource_savings, 4),
            "arm_stats": self._strategy.get_arm_stats(),
        }

    def save_state(self, path: Optional[str] = None) -> None:
        """持久化 MAB 状态到 JSON 文件。"""
        filepath = Path(path or self.state_path)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "mode": self.mode,
            "strategy": self._strategy.to_dict(),
            "current_arm": self._current_arm,
            "gop_since_last_anchor": self._gop_since_last_anchor,
            "total_decisions": self._total_decisions,
            "anchor_count": self._anchor_count,
        }

        with open(filepath, "w") as f:
            json.dump(state, f, indent=2)

        logger.info("MAB state saved to %s", filepath)

    def load_state(self, path: Optional[str] = None) -> bool:
        """
        从 JSON 文件加载 MAB 状态。

        Returns:
            True 表示成功加载，False 表示文件不存在或加载失败
        """
        filepath = Path(path or self.state_path)
        if not filepath.exists():
            return False

        try:
            with open(filepath) as f:
                state = json.load(f)

            strategy_data = state["strategy"]
            if strategy_data["type"] == "thompson":
                self._strategy = ThompsonStrategy.from_dict(strategy_data)
            else:
                self._strategy = UCBStrategy.from_dict(strategy_data)

            self._current_arm = state.get("current_arm", 0)
            self._gop_since_last_anchor = state.get("gop_since_last_anchor", 0)
            self._total_decisions = state.get("total_decisions", 0)
            self._anchor_count = state.get("anchor_count", 0)

            logger.info("MAB state loaded from %s", filepath)
            return True
        except Exception as e:
            logger.warning("Failed to load MAB state from %s: %s", filepath, e)
            return False
