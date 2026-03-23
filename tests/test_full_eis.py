"""
Full EIS unit tests — optical flow, anomaly detection, rule engine, and integration.

Run with:
    EIS_MODE=full pytest tests/test_full_eis.py -v
"""

import os
import time
from datetime import datetime, timezone

import numpy as np
import pytest

from services.adaptive_anchor import (
    AdaptiveAnchor,
    AnchorDecision,
    AnomalyDetector,
    AnomalyResult,
    EISRuleEngine,
    MotionFeatures,
    OpticalFlowAnalyzer,
)
from services.semantic_fingerprint import SemanticFingerprint


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_semantic(gop_id: int = 0, total_count: int = 0, objects: dict = None) -> SemanticFingerprint:
    """Create a SemanticFingerprint for testing."""
    if objects is None:
        objects = {"test_object": total_count} if total_count > 0 else {}
    timestamp = datetime.now(timezone.utc).isoformat()
    json_str = f'{{"gop_id":{gop_id},"total_count":{total_count}}}'
    return SemanticFingerprint(
        gop_id=gop_id,
        timestamp=timestamp,
        objects=objects,
        total_count=total_count,
        json_str=json_str,
        semantic_hash="a" * 64,
    )


def _black_frame(h: int = 480, w: int = 640) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


def _shifted_frame(base: np.ndarray, dx: int = 10) -> np.ndarray:
    """Shift a frame horizontally by dx pixels (with zero fill)."""
    shifted = np.zeros_like(base)
    if dx > 0:
        shifted[:, dx:, :] = base[:, :-dx, :]
    elif dx < 0:
        shifted[:, :dx, :] = base[:, -dx:, :]
    else:
        shifted[:] = base
    return shifted


# ---------------------------------------------------------------------------
# OpticalFlowAnalyzer tests
# ---------------------------------------------------------------------------


class TestOpticalFlowAnalyzer:
    def test_first_frame_returns_zeros(self):
        """First call (no previous frame) should return all-zero MotionFeatures."""
        analyzer = OpticalFlowAnalyzer()
        mf = analyzer.analyze(_black_frame())
        assert mf.magnitude_mean == 0.0
        assert mf.magnitude_max == 0.0
        assert mf.motion_area_ratio == 0.0

    def test_static_frames(self):
        """Two identical frames → near-zero magnitude."""
        analyzer = OpticalFlowAnalyzer()
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        analyzer.analyze(frame)  # first call sets prev
        mf = analyzer.analyze(frame.copy())

        assert mf.magnitude_mean < 0.5
        assert mf.motion_area_ratio < 0.05

    def test_motion_detected(self):
        """A horizontally shifted frame should produce measurable motion."""
        analyzer = OpticalFlowAnalyzer()
        # Use seeded random texture so optical flow has features to track
        rng = np.random.RandomState(42)
        base = rng.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        analyzer.analyze(base)
        shifted = _shifted_frame(base, dx=15)
        mf = analyzer.analyze(shifted)

        # Should detect significant motion
        assert mf.magnitude_mean > 1.0
        assert mf.motion_area_ratio > 0.1


# ---------------------------------------------------------------------------
# AnomalyDetector tests
# ---------------------------------------------------------------------------


class TestAnomalyDetector:
    def test_cold_start(self):
        """Fewer than 10 samples → anomaly_score = 0.0."""
        detector = AnomalyDetector(history_size=100, z_threshold=2.5)
        for i in range(9):
            result = detector.update(np.array([1.0, 0.5, 1.0, 0.1]))
            assert result.anomaly_score == 0.0
            assert result.is_anomaly is False

    def test_normal_then_anomaly(self):
        """50 similar vectors → low score; then one outlier → high score."""
        detector = AnomalyDetector(history_size=100, z_threshold=2.5)

        # Build baseline
        for i in range(50):
            result = detector.update(np.array([5.0, 2.0, 4.0, 0.3]))

        # After warm-up, normal input should have low score
        assert result.anomaly_score < 0.3

        # Feed an outlier
        outlier = np.array([50.0, 30.0, 60.0, 0.95])
        result = detector.update(outlier)
        assert result.anomaly_score > 0.5
        assert result.is_anomaly is True

    def test_z_scores_length(self):
        """z_scores list should match feature dimensionality."""
        detector = AnomalyDetector()
        for i in range(15):
            result = detector.update(np.array([1.0, 2.0, 3.0, 0.1]))
        assert len(result.z_scores) == 4


# ---------------------------------------------------------------------------
# EISRuleEngine tests
# ---------------------------------------------------------------------------


class TestEISRuleEngine:
    def test_weighted_low_activity(self):
        """Zero objects, no motion, no anomaly → low EIS."""
        engine = EISRuleEngine()
        sem = _make_semantic(total_count=0)
        motion = MotionFeatures(magnitude_mean=0.5)
        anomaly = AnomalyResult(anomaly_score=0.0)

        eis, breakdown = engine.compute_eis(sem, motion, anomaly)
        assert eis < 0.3
        assert breakdown["object"] == 0.1
        assert breakdown["motion"] == 0.1

    def test_weighted_high_activity(self):
        """Many objects + strong motion → high EIS."""
        engine = EISRuleEngine()
        sem = _make_semantic(total_count=10)
        motion = MotionFeatures(magnitude_mean=20.0, motion_area_ratio=0.5)
        anomaly = AnomalyResult(anomaly_score=0.3)

        eis, breakdown = engine.compute_eis(sem, motion, anomaly)
        assert eis > 0.7
        assert breakdown["object"] == 0.9
        assert breakdown["motion"] == 0.95

    def test_anomaly_override(self):
        """is_anomaly=True should force EIS >= 0.8."""
        engine = EISRuleEngine()
        sem = _make_semantic(total_count=0)
        motion = MotionFeatures(magnitude_mean=0.0)
        anomaly = AnomalyResult(anomaly_score=0.9, is_anomaly=True)

        eis, _ = engine.compute_eis(sem, motion, anomaly)
        assert eis >= 0.8

    def test_occlusion_override(self):
        """High motion_area_ratio + high magnitude → suspected occlusion → EIS=0.95."""
        engine = EISRuleEngine()
        sem = _make_semantic(total_count=0)
        motion = MotionFeatures(magnitude_mean=25.0, motion_area_ratio=0.95)
        anomaly = AnomalyResult(anomaly_score=0.0)

        eis, _ = engine.compute_eis(sem, motion, anomaly)
        assert eis == pytest.approx(0.95, abs=0.01)

    def test_person_bonus(self):
        """3+ persons should add +0.1 to object_signal."""
        engine = EISRuleEngine()
        sem_no_person = _make_semantic(total_count=3, objects={"car": 3})
        sem_with_person = _make_semantic(total_count=3, objects={"person": 3})
        motion = MotionFeatures(magnitude_mean=0.0)
        anomaly = AnomalyResult()

        eis_no, bd_no = engine.compute_eis(sem_no_person, motion, anomaly)
        eis_yes, bd_yes = engine.compute_eis(sem_with_person, motion, anomaly)

        assert bd_yes["object"] == pytest.approx(bd_no["object"] + 0.1, abs=0.01)

    def test_eis_clamped(self):
        """EIS should always be in [0.0, 1.0]."""
        engine = EISRuleEngine()
        sem = _make_semantic(total_count=100, objects={"person": 50})
        motion = MotionFeatures(magnitude_mean=50.0, motion_area_ratio=0.99)
        anomaly = AnomalyResult(anomaly_score=1.0, is_anomaly=True)

        eis, _ = engine.compute_eis(sem, motion, anomaly)
        assert 0.0 <= eis <= 1.0


# ---------------------------------------------------------------------------
# Full EIS integration tests
# ---------------------------------------------------------------------------


class TestFullEISIntegration:
    def test_full_mode_static_to_active(self):
        """20 GOPs: 10 static (black, 0 objects) + 10 active (shifted, objects present).

        EIS should transition from LOW toward MEDIUM/HIGH.
        """
        anchor = AdaptiveAnchor(eis_mode="full", upgrade_confirm=2, downgrade_confirm=3)

        # Static phase
        static_frame = _black_frame()
        decisions = []
        for i in range(10):
            sem = _make_semantic(gop_id=i, total_count=0)
            d = anchor.update(sem, keyframe=static_frame)
            decisions.append(d)

        # All should be LOW
        for d in decisions:
            assert d.level == "LOW"
            assert d.motion_features is not None
            assert d.anomaly_result is not None

        # Active phase — textured frame with shifting + objects
        base = np.random.randint(50, 200, (480, 640, 3), dtype=np.uint8)
        active_decisions = []
        for i in range(10):
            frame = _shifted_frame(base, dx=10 + i)
            sem = _make_semantic(gop_id=10 + i, total_count=8, objects={"person": 5, "car": 3})
            d = anchor.update(sem, keyframe=frame)
            active_decisions.append(d)

        # After enough active GOPs, should have escalated
        last = active_decisions[-1]
        assert last.eis_score > 0.3  # at least MEDIUM territory
        assert last.signal_breakdown is not None
        assert "object" in last.signal_breakdown

    def test_full_mode_has_signal_breakdown(self):
        """Full mode should populate signal_breakdown in AnchorDecision."""
        anchor = AdaptiveAnchor(eis_mode="full")
        frame = _black_frame()
        sem = _make_semantic(total_count=3)
        d = anchor.update(sem, keyframe=frame)

        # First frame yields zero motion, but signal_breakdown should exist
        assert d.signal_breakdown is not None
        assert set(d.signal_breakdown.keys()) == {"object", "motion", "anomaly"}


# ---------------------------------------------------------------------------
# Backward compatibility
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_lite_mode_default(self):
        """Default mode (no env var) should behave identically to original."""
        # Force lite mode explicitly
        anchor = AdaptiveAnchor(eis_mode="lite")

        # Zero count → EIS=0.1, LOW
        for i in range(5):
            sem = _make_semantic(gop_id=i, total_count=0)
            d = anchor.update(sem)

        assert d.eis_score == 0.1
        assert d.level == "LOW"
        assert d.motion_features is None
        assert d.anomaly_result is None
        assert d.signal_breakdown is None

    def test_lite_ignores_keyframe(self):
        """Lite mode should produce same result regardless of keyframe arg."""
        anchor = AdaptiveAnchor(eis_mode="lite")
        frame = _black_frame()

        sem = _make_semantic(gop_id=0, total_count=3)
        d1 = anchor.update(sem)

        anchor2 = AdaptiveAnchor(eis_mode="lite")
        d2 = anchor2.update(sem, keyframe=frame)

        assert d1.eis_score == d2.eis_score
        assert d1.level == d2.level

    def test_lite_eis_values(self):
        """Verify EIS values match original 3-tier mapping."""
        anchor = AdaptiveAnchor(eis_mode="lite")

        # 0 objects → 0.1
        sem = _make_semantic(total_count=0)
        d = anchor.update(sem)
        assert d.eis_score == 0.1

        # Reset anchor for next test
        anchor2 = AdaptiveAnchor(eis_mode="lite")
        sem = _make_semantic(total_count=3)
        d = anchor2.update(sem)
        assert d.eis_score == 0.5

        anchor3 = AdaptiveAnchor(eis_mode="lite")
        sem = _make_semantic(total_count=8)
        d = anchor3.update(sem)
        assert d.eis_score == 0.9

    def test_lite_upgrade_downgrade_timing(self):
        """Verify upgrade=3, downgrade=5 timing in lite mode matches original."""
        anchor = AdaptiveAnchor(eis_mode="lite")

        # LOW → HIGH via counts of 8
        counts = [0] * 3 + [8] * 12
        decisions = []
        for i, c in enumerate(counts):
            sem = _make_semantic(gop_id=i, total_count=c)
            decisions.append(anchor.update(sem))

        # First 5 should be LOW
        for i in range(5):
            assert decisions[i].level == "LOW"

        # Should eventually reach HIGH
        assert decisions[8].level == "HIGH"
