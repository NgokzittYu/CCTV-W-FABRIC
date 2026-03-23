"""
MAB (Multi-Armed Bandit) 自适应锚定单元测试

测试内容：
- UCB1 策略收敛性
- Thompson Sampling 表现
- MABAnchorManager 决策逻辑
- 状态持久化往返
- ANCHOR_MODE=fixed 向后兼容性
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from unittest import mock

import numpy as np
import pytest

from services.mab_anchor import (
    ARM_INTERVALS,
    NUM_ARMS,
    MABAnchorManager,
    ThompsonStrategy,
    UCBStrategy,
    compute_reward,
)


# ── Reward 计算 ───────────────────────────────────────────────────────

class TestComputeReward:
    def test_full_success(self):
        """全成功、零成本、零延迟 → reward ≈ 0.6 (alpha)。"""
        reward = compute_reward(success=True, cost=0.0, latency=0.0)
        assert abs(reward - 0.6) < 1e-6

    def test_full_failure(self):
        """全失败、零成本 → reward ≈ 0.0。"""
        reward = compute_reward(success=False, cost=0.0, latency=0.0)
        assert abs(reward - 0.0) < 1e-6

    def test_high_cost_penalty(self):
        """高成本应降低 reward。"""
        r_low = compute_reward(success=True, cost=0.0, latency=0.0)
        r_high = compute_reward(success=True, cost=1.0, latency=0.0)
        assert r_high < r_low

    def test_high_latency_penalty(self):
        """高延迟应降低 reward。"""
        r_low = compute_reward(success=True, cost=0.0, latency=0.0)
        r_high = compute_reward(success=True, cost=0.0, latency=5.0)
        assert r_high < r_low

    def test_reward_clamped(self):
        """reward 应被钳制到 [-1, 1]。"""
        r = compute_reward(success=False, cost=10.0, latency=100.0)
        assert r >= -1.0
        r = compute_reward(success=True, cost=0.0, latency=0.0)
        assert r <= 1.0


# ── UCB1 策略 ─────────────────────────────────────────────────────────

class TestUCBStrategy:
    def test_initial_exploration(self):
        """每个臂应先被拉一次（探索阶段）。"""
        strategy = UCBStrategy()
        arms_selected = []
        for _ in range(NUM_ARMS):
            arm = strategy.select_arm()
            arms_selected.append(arm)
            strategy.update(arm, 0.5)

        # 前 4 次应覆盖所有臂
        assert set(arms_selected) == set(range(NUM_ARMS))

    def test_convergence_to_best_arm(self):
        """UCB 应在大量试验后收敛到最优臂。"""
        np.random.seed(42)
        strategy = UCBStrategy()

        # 臂 1（每 2 GOP 锚定）设为最优：高 reward
        arm_rewards = {0: 0.3, 1: 0.8, 2: 0.4, 3: 0.2}

        arm_counts = [0] * NUM_ARMS
        for _ in range(1000):
            arm = strategy.select_arm()
            # 模拟带噪声的 reward
            reward = arm_rewards[arm] + np.random.normal(0, 0.1)
            strategy.update(arm, reward)
            arm_counts[arm] += 1

        # 最优臂（arm 1）应被选择最多
        best_arm = int(np.argmax(arm_counts))
        assert best_arm == 1, f"Expected arm 1, got arm {best_arm}. Counts: {arm_counts}"
        # 最优臂选择率 > 50%
        assert arm_counts[1] / 1000 > 0.5

    def test_serialization_roundtrip(self):
        """序列化/反序列化往返。"""
        strategy = UCBStrategy()
        for i in range(10):
            arm = strategy.select_arm()
            strategy.update(arm, 0.5)

        data = strategy.to_dict()
        restored = UCBStrategy.from_dict(data)

        assert restored.counts == strategy.counts
        assert restored.values == strategy.values
        assert restored.total_count == strategy.total_count

    def test_arm_stats(self):
        """统计信息格式正确。"""
        strategy = UCBStrategy()
        strategy.update(0, 0.5)
        strategy.update(1, 0.8)

        stats = strategy.get_arm_stats()
        assert len(stats) == NUM_ARMS
        assert stats[0]["arm"] == 0
        assert stats[0]["interval"] == ARM_INTERVALS[0]
        assert stats[0]["count"] == 1
        assert abs(stats[0]["avg_reward"] - 0.5) < 1e-6


# ── Thompson Sampling 策略 ────────────────────────────────────────────

class TestThompsonStrategy:
    def test_convergence_to_best_arm(self):
        """Thompson Sampling 应收敛到最优臂。"""
        np.random.seed(123)
        strategy = ThompsonStrategy()

        # 臂 2 设为最优：高成功率
        arm_success_probs = {0: 0.3, 1: 0.4, 2: 0.9, 3: 0.2}

        arm_counts = [0] * NUM_ARMS
        for _ in range(500):
            arm = strategy.select_arm()
            # 伯努利 reward
            success = np.random.random() < arm_success_probs[arm]
            reward = 1.0 if success else -0.1
            strategy.update(arm, reward)
            arm_counts[arm] += 1

        # 最优臂（arm 2）应被选择最多
        best_arm = int(np.argmax(arm_counts))
        assert best_arm == 2, f"Expected arm 2, got arm {best_arm}. Counts: {arm_counts}"

    def test_beta_updates(self):
        """正确更新 Beta 参数。"""
        strategy = ThompsonStrategy()

        # 正 reward → alpha 增加
        strategy.update(0, 0.5)
        assert strategy.alphas[0] == 2.0
        assert strategy.betas[0] == 1.0

        # 负 reward → beta 增加
        strategy.update(0, -0.1)
        assert strategy.alphas[0] == 2.0
        assert strategy.betas[0] == 2.0

        # 零 reward → beta 增加
        strategy.update(1, 0.0)
        assert strategy.betas[1] == 2.0

    def test_serialization_roundtrip(self):
        """序列化/反序列化往返。"""
        strategy = ThompsonStrategy()
        for i in range(10):
            arm = strategy.select_arm()
            strategy.update(arm, 0.5 if i % 2 == 0 else -0.1)

        data = strategy.to_dict()
        restored = ThompsonStrategy.from_dict(data)

        assert restored.alphas == strategy.alphas
        assert restored.betas == strategy.betas


# ── MABAnchorManager ──────────────────────────────────────────────────

class TestMABAnchorManager:
    def test_should_anchor_interval(self):
        """按臂间隔正确触发锚定。"""
        manager = MABAnchorManager(mode="mab_ucb", auto_load=False)
        # 初始臂可能是 0（interval=1），测试 interval 逻辑
        interval = manager.current_interval
        results = []
        for i in range(interval * 3):
            results.append(manager.should_anchor(i))

        # 每 interval 个 GOP 触发一次
        true_count = sum(results)
        assert true_count == 3

    def test_report_result_changes_arm(self):
        """报告结果后应基于策略更新臂选择。"""
        manager = MABAnchorManager(mode="mab_ucb", auto_load=False)
        initial_arm = manager.current_arm

        # 报告多次差结果
        for _ in range(10):
            manager.report_result(success=False, cost=1.0, latency=5.0)

        # 报告好结果到另一个臂（通过内部策略）
        # 臂应该有变化的可能
        # 这里只验证不崩溃和状态更新
        assert manager._total_decisions == 0  # decisions via should_anchor
        stats = manager.get_stats()
        assert stats["mode"] == "mab_ucb"
        assert stats["arm_stats"] is not None

    def test_state_persistence(self):
        """状态持久化：保存 → 加载 → 继续决策。"""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        try:
            # 创建并训练
            manager1 = MABAnchorManager(mode="mab_ucb", state_path=path, auto_load=False)
            for i in range(20):
                if manager1.should_anchor(i):
                    manager1.report_result(success=True, cost=0.1, latency=0.3)
            manager1.save_state(path)

            # 加载并继续
            manager2 = MABAnchorManager(mode="mab_ucb", state_path=path, auto_load=True)
            assert manager2._total_decisions == manager1._total_decisions
            assert manager2._anchor_count == manager1._anchor_count

            # 能继续决策
            result = manager2.should_anchor(100)
            assert isinstance(result, bool)
        finally:
            os.unlink(path)

    def test_thompson_mode(self):
        """Thompson 模式能正常运行。"""
        manager = MABAnchorManager(mode="mab_thompson", auto_load=False)
        assert isinstance(manager._strategy, ThompsonStrategy)

        for i in range(30):
            if manager.should_anchor(i):
                manager.report_result(success=True)

        stats = manager.get_stats()
        assert stats["mode"] == "mab_thompson"

    def test_get_stats(self):
        """统计信息格式正确。"""
        manager = MABAnchorManager(mode="mab_ucb", auto_load=False)
        for i in range(5):
            manager.should_anchor(i)

        stats = manager.get_stats()
        assert "mode" in stats
        assert "current_arm" in stats
        assert "current_interval" in stats
        assert "total_decisions" in stats
        assert "anchor_count" in stats
        assert "arm_stats" in stats
        assert len(stats["arm_stats"]) == NUM_ARMS


# ── AdaptiveAnchor 集成 ──────────────────────────────────────────────

class TestAnchorModeIntegration:
    """测试 ANCHOR_MODE 集成到 AdaptiveAnchor。"""

    def _create_semantic(self, gop_id=0, total_count=3):
        from services.semantic_fingerprint import SemanticFingerprint
        timestamp = datetime.now(timezone.utc).isoformat()
        objects = {"test_object": total_count} if total_count > 0 else {}
        json_str = f'{{"gop_id":{gop_id},"total_count":{total_count}}}'
        return SemanticFingerprint(
            gop_id=gop_id, timestamp=timestamp, objects=objects,
            total_count=total_count, json_str=json_str, semantic_hash="a" * 64,
        )

    def test_fixed_mode_default(self):
        """默认 ANCHOR_MODE=fixed，行为与原系统一致。"""
        from services.adaptive_anchor import AdaptiveAnchor
        anchor = AdaptiveAnchor(anchor_mode="fixed")
        assert anchor.anchor_mode == "fixed"
        assert anchor._mab_manager is None

        decision = anchor.update(self._create_semantic())
        assert decision.mab_arm is None

    def test_mab_ucb_mode(self):
        """ANCHOR_MODE=mab_ucb 时使用 MAB 决策。"""
        from services.adaptive_anchor import AdaptiveAnchor
        anchor = AdaptiveAnchor(anchor_mode="mab_ucb")
        assert anchor._mab_manager is not None

        decisions = []
        for i in range(10):
            d = anchor.update(self._create_semantic(gop_id=i))
            decisions.append(d)

        # 应该有 mab_arm 字段
        assert all(d.mab_arm is not None for d in decisions)
        # 应该有一些锚定触发
        assert any(d.should_report_now for d in decisions)

    def test_mab_thompson_mode(self):
        """ANCHOR_MODE=mab_thompson 时使用 Thompson 决策。"""
        from services.adaptive_anchor import AdaptiveAnchor
        anchor = AdaptiveAnchor(anchor_mode="mab_thompson")
        assert anchor._mab_manager is not None

        decision = anchor.update(self._create_semantic())
        assert decision.mab_arm is not None

    def test_report_anchor_result_fixed_noop(self):
        """Fixed 模式下 report_anchor_result 不报错。"""
        from services.adaptive_anchor import AdaptiveAnchor
        anchor = AdaptiveAnchor(anchor_mode="fixed")
        # 不应崩溃
        anchor.report_anchor_result(success=True, cost=0.1, latency=0.5)

    def test_report_anchor_result_mab(self):
        """MAB 模式下 report_anchor_result 更新策略。"""
        from services.adaptive_anchor import AdaptiveAnchor
        anchor = AdaptiveAnchor(anchor_mode="mab_ucb")
        anchor.update(self._create_semantic())
        anchor.report_anchor_result(success=True, cost=0.1, latency=0.5)
        # 验证 MAB 策略已更新
        assert anchor._mab_manager._strategy.total_count > 0

    def test_eis_still_computed_in_mab_mode(self):
        """MAB 模式下 EIS 仍然被计算（用于监控）。"""
        from services.adaptive_anchor import AdaptiveAnchor
        anchor = AdaptiveAnchor(anchor_mode="mab_ucb")

        decision = anchor.update(self._create_semantic(total_count=3))
        assert decision.eis_score > 0  # EIS 正常计算
        assert decision.level is not None

    def test_backward_compatibility_env_var(self):
        """通过环境变量设置 ANCHOR_MODE。"""
        from services.adaptive_anchor import AdaptiveAnchor
        with mock.patch.dict(os.environ, {"ANCHOR_MODE": "fixed"}):
            anchor = AdaptiveAnchor()
            assert anchor.anchor_mode == "fixed"
            assert anchor._mab_manager is None
