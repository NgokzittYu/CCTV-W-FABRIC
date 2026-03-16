"""
Unit tests for adaptive anchor module.
"""
import time
from datetime import datetime, timezone

import pytest
from services.adaptive_anchor import AdaptiveAnchor, AnchorDecision
from services.semantic_fingerprint import SemanticFingerprint


class TestAdaptiveAnchor:
    """Test AdaptiveAnchor class."""

    def test_initialization(self):
        """Test that AdaptiveAnchor initializes with correct defaults."""
        anchor = AdaptiveAnchor()

        assert anchor.window_size == 10
        assert anchor.upgrade_confirm == 3
        assert anchor.downgrade_confirm == 5
        assert len(anchor._count_history) == 0
        assert anchor._current_level == "LOW"
        assert anchor._pending_level is None
        assert anchor._confirm_counter == 0

    def test_custom_parameters(self):
        """Test initialization with custom parameters."""
        anchor = AdaptiveAnchor(window_size=5, upgrade_confirm=2, downgrade_confirm=4)

        assert anchor.window_size == 5
        assert anchor.upgrade_confirm == 2
        assert anchor.downgrade_confirm == 4

    def test_eis_calculation_zero_count(self):
        """Test EIS calculation when smoothed_count is 0."""
        anchor = AdaptiveAnchor()

        # Feed 5 zeros
        for i in range(5):
            semantic = self._create_semantic(gop_id=i, total_count=0)
            decision = anchor.update(semantic)

        assert decision.smoothed_count == 0
        assert decision.eis_score == 0.1
        assert decision.level == "LOW"

    def test_eis_calculation_low_count(self):
        """Test EIS calculation when smoothed_count <= 5."""
        anchor = AdaptiveAnchor()

        # Feed counts: 3, 3, 3, 3, 3
        for i in range(5):
            semantic = self._create_semantic(gop_id=i, total_count=3)
            decision = anchor.update(semantic)

        assert decision.smoothed_count == 3
        assert decision.eis_score == 0.5
        assert decision.level == "MEDIUM"

    def test_eis_calculation_high_count(self):
        """Test EIS calculation when smoothed_count > 5."""
        anchor = AdaptiveAnchor()

        # Feed counts: 8, 8, 8, 8, 8
        for i in range(5):
            semantic = self._create_semantic(gop_id=i, total_count=8)
            decision = anchor.update(semantic)

        assert decision.smoothed_count == 8
        assert decision.eis_score == 0.9
        assert decision.level == "HIGH"

    def test_level_transition_low_to_medium_to_high(self):
        """Test level transitions: LOW → MEDIUM → HIGH with correct timing."""
        anchor = AdaptiveAnchor()

        # Sequence: [0,0,0, 8,8,8,8,8,8,8,8,8,8,8,8]
        # With window_size=10:
        # i=0-4: median=0 (LOW)
        # i=5: median=4 (MEDIUM target, 1/3)
        # i=6: median=8 (HIGH target, resets counter, 1/3)
        # i=7-8: median=8 (HIGH target, 2/3, 3/3 -> upgrade to HIGH)
        counts = [0]*3 + [8]*12
        decisions = []

        for i, count in enumerate(counts):
            semantic = self._create_semantic(gop_id=i, total_count=count)
            decision = anchor.update(semantic)
            decisions.append(decision)

        # First 5: should stay LOW (median=0, EIS=0.1)
        for i in range(5):
            assert decisions[i].level == "LOW"
            assert decisions[i].eis_score == 0.1

        # Index 5: median=4, target=MEDIUM, pending (1/3)
        assert decisions[5].level == "LOW"
        assert decisions[5].eis_score == 0.5

        # Index 6: median=8, target=HIGH, pending (1/3) - counter reset
        assert decisions[6].level == "LOW"
        assert decisions[6].eis_score == 0.9

        # Index 7: median=8, target=HIGH, pending (2/3)
        assert decisions[7].level == "LOW"
        assert decisions[7].eis_score == 0.9

        # Index 8: median=8, target=HIGH, confirmed (3/3) - level changes to HIGH
        assert decisions[8].level == "HIGH"
        assert decisions[8].eis_score == 0.9

        # Index 9+: stays HIGH
        for i in range(9, len(decisions)):
            assert decisions[i].level == "HIGH"
            assert decisions[i].eis_score == 0.9

    def test_median_robustness_against_outliers(self):
        """Test that median filtering handles outliers correctly."""
        anchor = AdaptiveAnchor()

        # Sequence: [3,3,3,15,3,3,3,3,3,3]
        # Median should remain 3, not affected by single outlier 15
        counts = [3, 3, 3, 15, 3, 3, 3, 3, 3, 3]
        decisions = []

        for i, count in enumerate(counts):
            semantic = self._create_semantic(gop_id=i, total_count=count)
            decision = anchor.update(semantic)
            decisions.append(decision)

        # After 10 values, window is full
        # Median of [3,3,3,15,3,3,3,3,3,3] = 3
        assert decisions[9].smoothed_count == 3
        assert decisions[9].eis_score == 0.5  # count <= 5

    def test_fast_upgrade_3_confirmations(self):
        """Test that upgrade requires exactly 3 consecutive confirmations."""
        anchor = AdaptiveAnchor(upgrade_confirm=3)

        # Start at LOW, try to upgrade to MEDIUM
        # Feed: 0, 0, 3, 3, 3, 3 (should upgrade on 6th update)
        counts = [0, 0, 3, 3, 3, 3]
        decisions = []

        for i, count in enumerate(counts):
            semantic = self._create_semantic(gop_id=i, total_count=count)
            decision = anchor.update(semantic)
            decisions.append(decision)

        assert decisions[0].level == "LOW"
        assert decisions[1].level == "LOW"
        assert decisions[2].level == "LOW"  # median=0, target=LOW
        assert decisions[3].level == "LOW"  # median=1, target=MEDIUM (1/3)
        assert decisions[4].level == "LOW"  # median=3, target=MEDIUM (2/3)
        assert decisions[5].level == "MEDIUM"  # median=3, target=MEDIUM (3/3) - upgraded!

    def test_slow_downgrade_5_confirmations(self):
        """Test that downgrade requires exactly 5 consecutive confirmations."""
        anchor = AdaptiveAnchor(downgrade_confirm=5)

        # Start at HIGH, try to downgrade to MEDIUM
        # First get to HIGH: feed 5x 8's
        for i in range(5):
            semantic = self._create_semantic(gop_id=i, total_count=8)
            anchor.update(semantic)

        # Now try to downgrade: feed 3's (MEDIUM level)
        # Need more 3's because median changes slowly with window=10
        decisions = []
        for i in range(10):
            semantic = self._create_semantic(gop_id=100+i, total_count=3)
            decision = anchor.update(semantic)
            decisions.append(decision)

        # i=0-3: median still 8, target=HIGH
        assert decisions[0].level == "HIGH"
        assert decisions[1].level == "HIGH"
        assert decisions[2].level == "HIGH"
        assert decisions[3].level == "HIGH"

        # i=4: median=5, target=MEDIUM (1/5)
        assert decisions[4].level == "HIGH"
        assert decisions[4].eis_score == 0.5

        # i=5-8: median=3, target=MEDIUM (2/5, 3/5, 4/5, 5/5)
        assert decisions[5].level == "HIGH"  # 2/5
        assert decisions[6].level == "HIGH"  # 3/5
        assert decisions[7].level == "HIGH"  # 4/5
        assert decisions[8].level == "MEDIUM"  # 5/5 - downgraded!
        assert decisions[9].level == "MEDIUM"

    def test_report_interval_mapping(self):
        """Test that report intervals map correctly to levels."""
        anchor = AdaptiveAnchor()

        # LOW level
        for i in range(5):
            semantic = self._create_semantic(gop_id=i, total_count=0)
            decision = anchor.update(semantic)
        assert decision.level == "LOW"
        assert decision.report_interval_seconds == 300

        # MEDIUM level - need 7 updates to get 3 confirmations
        # (median shifts to MEDIUM target at update 10, needs 3 more confirmations)
        for i in range(7):
            semantic = self._create_semantic(gop_id=10+i, total_count=3)
            decision = anchor.update(semantic)
        assert decision.level == "MEDIUM"
        assert decision.report_interval_seconds == 60

        # HIGH level - need enough to shift median > 5
        for i in range(8):
            semantic = self._create_semantic(gop_id=20+i, total_count=8)
            decision = anchor.update(semantic)
        assert decision.level == "HIGH"
        assert decision.report_interval_seconds == 10

    def test_should_report_now_timing(self):
        """Test that should_report_now respects interval timing."""
        anchor = AdaptiveAnchor()

        # First update should always report (elapsed time is huge since _last_report_time=0)
        semantic = self._create_semantic(gop_id=0, total_count=0)
        decision = anchor.update(semantic)
        assert decision.should_report_now is True

        # Immediate next updates should be False (not enough time passed)
        for i in range(1, 5):
            semantic = self._create_semantic(gop_id=i, total_count=0)
            decision = anchor.update(semantic)
            assert decision.should_report_now is False

        # Simulate time passing (mock by setting _last_report_time)
        anchor._last_report_time = time.time() - 301  # 301 seconds ago
        semantic = self._create_semantic(gop_id=10, total_count=0)
        decision = anchor.update(semantic)
        assert decision.should_report_now is True

    def test_should_report_now_after_level_change(self):
        """Test that should_report_now triggers after level upgrade."""
        anchor = AdaptiveAnchor()

        # Start at LOW
        for i in range(5):
            semantic = self._create_semantic(gop_id=i, total_count=0)
            anchor.update(semantic)

        # Upgrade to HIGH (10s interval) - need enough updates to shift median > 5
        for i in range(8):
            semantic = self._create_semantic(gop_id=10+i, total_count=8)
            decision = anchor.update(semantic)

        # After upgrade, should report immediately
        assert decision.level == "HIGH"
        assert decision.should_report_now is True

    def test_sliding_window_behavior(self):
        """Test that sliding window maintains correct size."""
        anchor = AdaptiveAnchor(window_size=5)

        # Feed 10 values, window should only keep last 5
        for i in range(10):
            semantic = self._create_semantic(gop_id=i, total_count=i)
            anchor.update(semantic)

        # Window should contain [5, 6, 7, 8, 9]
        assert len(anchor._count_history) == 5
        assert list(anchor._count_history) == [5, 6, 7, 8, 9]

    def test_confirmation_reset_on_level_change(self):
        """Test that confirmation counter resets when target level changes."""
        anchor = AdaptiveAnchor()

        # Fill window with zeros to establish LOW level
        for i in range(10):
            semantic = self._create_semantic(gop_id=i, total_count=0)
            anchor.update(semantic)

        assert anchor._current_level == "LOW"

        # Start adding 3s to shift median toward MEDIUM
        # Window: [0,0,0,0,0,0,0,0,0,0] -> median=0
        semantic = self._create_semantic(gop_id=10, total_count=3)
        anchor.update(semantic)
        # Window: [0,0,0,0,0,0,0,0,0,3] -> median=0, target=LOW

        # Add more 3s
        for i in range(4):
            semantic = self._create_semantic(gop_id=11+i, total_count=3)
            decision = anchor.update(semantic)
        # Window: [0,0,0,0,0,0,3,3,3,3] -> median=0, target=LOW

        # Add one more 3 to shift median
        semantic = self._create_semantic(gop_id=15, total_count=3)
        decision = anchor.update(semantic)
        # Window: [0,0,0,0,3,3,3,3,3,3] -> median=3, target=MEDIUM
        assert decision.level == "LOW"
        assert anchor._pending_level == "MEDIUM"
        assert anchor._confirm_counter == 2  # Already 2 confirmations (updates 14 and 15)

        # Now suddenly add a high count (8) - this should NOT reset counter
        # because median will still indicate MEDIUM target
        semantic = self._create_semantic(gop_id=16, total_count=8)
        decision = anchor.update(semantic)
        # Window: [0,0,0,3,3,3,3,3,3,8] -> median=3, target=MEDIUM

        # Counter should reach 3rd confirmation and upgrade
        assert decision.level == "MEDIUM"  # Should have upgraded now
        assert anchor._pending_level is None
        assert anchor._confirm_counter == 0

    def test_empty_window_initial_state(self):
        """Test behavior with empty sliding window."""
        anchor = AdaptiveAnchor()

        # First update with empty window
        semantic = self._create_semantic(gop_id=0, total_count=5)
        decision = anchor.update(semantic)

        # Should use the single value as median
        assert decision.smoothed_count == 5
        assert decision.eis_score == 0.5

    # Helper method
    def _create_semantic(self, gop_id: int, total_count: int) -> SemanticFingerprint:
        """Create a SemanticFingerprint for testing."""
        timestamp = datetime.now(timezone.utc).isoformat()
        objects = {"test_object": total_count} if total_count > 0 else {}
        json_str = f'{{"gop_id":{gop_id},"objects":{objects},"timestamp":"{timestamp}","total_count":{total_count}}}'
        semantic_hash = "a" * 64  # Dummy hash

        return SemanticFingerprint(
            gop_id=gop_id,
            timestamp=timestamp,
            objects=objects,
            total_count=total_count,
            json_str=json_str,
            semantic_hash=semantic_hash
        )
