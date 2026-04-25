import os
import tempfile

import pytest

from services.mab_anchor import (
    ARM_INTERVALS,
    MABAnchorManager,
    ThompsonStrategy,
    UCBStrategy,
    compute_reward,
    estimate_resource_savings,
)


pytestmark = pytest.mark.unit


def _manager_for_arm(arm: int) -> MABAnchorManager:
    manager = MABAnchorManager(mode="mab_ucb", auto_load=False)
    manager._current_arm = arm
    manager._gop_since_last_anchor = 0
    manager._total_decisions = 0
    manager._anchor_count = 0
    return manager


def test_compute_reward_penalizes_cost_and_latency():
    ideal = compute_reward(success=True, cost=0.0, latency=0.0)
    costly = compute_reward(success=True, cost=1.0, latency=5.0)
    failed = compute_reward(success=False, cost=0.0, latency=0.0)

    assert ideal == pytest.approx(0.6)
    assert costly < ideal
    assert failed == pytest.approx(0.0)


def test_ucb_strategy_explores_all_arms_once():
    strategy = UCBStrategy()
    selected = []

    for _ in ARM_INTERVALS:
        arm = strategy.select_arm()
        selected.append(arm)
        strategy.update(arm, 0.5)

    assert selected == [0, 1, 2, 3]


def test_thompson_strategy_updates_beta_parameters():
    strategy = ThompsonStrategy()

    strategy.update(0, 0.5)
    strategy.update(0, -0.1)

    assert strategy.alphas[0] == 2.0
    assert strategy.betas[0] == 2.0


def test_estimate_resource_savings_by_interval():
    expected = {1: 0.0, 2: 50.0, 5: 80.0, 10: 90.0}

    assert ARM_INTERVALS == [1, 2, 5, 10]
    for interval, saving in expected.items():
        assert estimate_resource_savings(interval) == pytest.approx(saving)


def test_manager_stats_include_estimated_resource_savings():
    manager = _manager_for_arm(2)

    stats = manager.get_stats()

    assert stats["current_interval"] == 5
    assert stats["estimated_resource_savings_percent"] == pytest.approx(80.0)
    assert stats["actual_anchor_rate_percent"] == pytest.approx(0.0)
    assert stats["actual_resource_savings_percent"] == pytest.approx(0.0)


@pytest.mark.parametrize(
    ("arm", "expected_anchors", "expected_savings"),
    [(0, 100, 0.0), (1, 50, 50.0), (2, 20, 80.0), (3, 10, 90.0)],
)
def test_actual_resource_savings_from_anchor_decisions(arm, expected_anchors, expected_savings):
    manager = _manager_for_arm(arm)

    for gop_index in range(100):
        manager.should_anchor(gop_index)

    stats = manager.get_stats()

    assert stats["anchor_count"] == expected_anchors
    assert stats["total_decisions"] == 100
    assert stats["actual_anchor_rate_percent"] == pytest.approx(100.0 - expected_savings)
    assert stats["actual_resource_savings_percent"] == pytest.approx(expected_savings)


def test_state_persistence_roundtrip():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        first = MABAnchorManager(mode="mab_ucb", state_path=path, auto_load=False)
        for i in range(12):
            if first.should_anchor(i):
                first.report_result(success=True, cost=0.1, latency=0.2)
        first.save_state(path)

        restored = MABAnchorManager(mode="mab_ucb", state_path=path, auto_load=True)

        assert restored.get_stats()["total_decisions"] == first.get_stats()["total_decisions"]
        assert restored.get_stats()["anchor_count"] == first.get_stats()["anchor_count"]
    finally:
        os.unlink(path)
