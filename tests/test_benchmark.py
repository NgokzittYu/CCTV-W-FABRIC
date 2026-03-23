"""
Benchmark 框架单元测试。

测试内容：
- 指标计算正确性
- 合成数据生成
- 报告格式输出
- 最小场景运行
"""

import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pytest

from benchmarks.config import BenchmarkConfig
from benchmarks.datasets import (
    SyntheticGOP,
    apply_tamper,
    generate_dataset,
    generate_frame,
    generate_gop,
)
from benchmarks.metrics import (
    ClassificationMetrics,
    LatencyStats,
    ResourceSnapshot,
    ThroughputStats,
    measure_time,
)


# ── Metrics ───────────────────────────────────────────────────────────

class TestLatencyStats:
    def test_empty(self):
        stats = LatencyStats()
        assert stats.count == 0
        assert stats.mean == 0.0

    def test_percentiles(self):
        stats = LatencyStats(values_ms=list(range(1, 101)))
        assert stats.count == 100
        assert abs(stats.p50 - 50.5) < 1
        assert stats.p95 >= 95
        assert stats.p99 >= 99
        assert stats.min == 1.0
        assert stats.max == 100.0

    def test_to_dict(self):
        stats = LatencyStats(values_ms=[1.0, 2.0, 3.0])
        d = stats.to_dict()
        assert "mean_ms" in d
        assert "p50_ms" in d
        assert "p95_ms" in d
        assert "count" in d
        assert d["count"] == 3


class TestThroughputStats:
    def test_items_per_second(self):
        stats = ThroughputStats(total_items=100, total_seconds=2.0)
        assert stats.items_per_second == 50.0

    def test_zero_seconds(self):
        stats = ThroughputStats(total_items=0, total_seconds=0.0)
        assert stats.items_per_second == 0.0


class TestClassificationMetrics:
    def test_perfect_classifier(self):
        m = ClassificationMetrics(tp=50, fp=0, tn=50, fn=0)
        assert m.tpr == 1.0
        assert m.fpr == 0.0
        assert m.precision == 1.0
        assert m.f1 == 1.0
        assert m.accuracy == 1.0

    def test_random_classifier(self):
        m = ClassificationMetrics(tp=25, fp=25, tn=25, fn=25)
        assert abs(m.tpr - 0.5) < 1e-6
        assert abs(m.fpr - 0.5) < 1e-6

    def test_to_dict(self):
        m = ClassificationMetrics(tp=10, fp=2, tn=8, fn=5)
        d = m.to_dict()
        assert "tpr" in d
        assert "fpr" in d
        assert "f1" in d


class TestMeasureTime:
    def test_context_manager(self):
        import time
        with measure_time() as t:
            time.sleep(0.01)
        assert t["elapsed_ms"] > 5  # 至少 5ms


class TestResourceSnapshot:
    def test_capture(self):
        snap = ResourceSnapshot.capture()
        assert snap.memory_mb > 0
        assert snap.to_dict()["memory_mb"] > 0


# ── Datasets ──────────────────────────────────────────────────────────

class TestDatasets:
    def test_generate_frame(self):
        frame = generate_frame(640, 480, seed=42)
        assert frame.shape == (480, 640, 3)
        assert frame.dtype == np.uint8

    def test_generate_gop(self):
        gop = generate_gop(0, 640, 480, 15)
        assert isinstance(gop, SyntheticGOP)
        assert len(gop.frames) == 15
        assert len(gop.sha256_hash) == 64

    def test_generate_dataset(self):
        ds = generate_dataset(5, 320, 240, 10)
        assert len(ds) == 5
        assert all(g.frame_count == 10 for g in ds)

    def test_deterministic(self):
        g1 = generate_gop(0, 320, 240, seed=42)
        g2 = generate_gop(0, 320, 240, seed=42)
        assert g1.sha256_hash == g2.sha256_hash

    def test_apply_tamper_frame_replace(self):
        orig = generate_frame(320, 240, seed=0)
        tampered = apply_tamper(orig, "frame_replace", intensity=0.5)
        assert not np.array_equal(orig, tampered)

    def test_apply_tamper_all_types(self):
        orig = generate_frame(320, 240, seed=0)
        for t_type in ["frame_replace", "content_overlay", "temporal_shift", "compression", "noise_inject"]:
            tampered = apply_tamper(orig, t_type, intensity=0.5)
            assert tampered.shape == orig.shape
            assert tampered.dtype == orig.dtype


# ── Config ────────────────────────────────────────────────────────────

class TestConfig:
    def test_defaults(self):
        cfg = BenchmarkConfig()
        assert cfg.rounds == 3
        assert "720p" in cfg.resolutions

    def test_output_dir_created(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = BenchmarkConfig(output_dir=Path(tmpdir) / "sub")
            assert cfg.output_dir.exists()


# ── Baselines ─────────────────────────────────────────────────────────

class TestBaselines:
    def test_naive_hash(self):
        from benchmarks.baselines.naive_hash import compute_hash, detect_tamper
        f = generate_frame(320, 240, seed=0)
        h = compute_hash(f)
        assert len(h) == 64
        assert not detect_tamper(h, h)
        assert detect_tamper(h, "different")

    def test_simple_merkle(self):
        from benchmarks.baselines.simple_merkle import build_flat_merkle
        hashes = ["aaa", "bbb", "ccc", "ddd"]
        root, levels = build_flat_merkle(hashes)
        assert len(root) == 64
        assert len(levels) >= 2

    def test_fixed_anchor(self):
        from benchmarks.baselines.fixed_anchor import FixedAnchor
        anchor = FixedAnchor(interval=5)
        results = [anchor.should_anchor(i) for i in range(15)]
        assert sum(results) == 3


# ── Report ────────────────────────────────────────────────────────────

class TestLatexTable:
    def test_throughput_table(self):
        from benchmarks.report.latex_table import generate_throughput_table
        data = {
            "throughput_by_resolution": {
                "720p": {
                    "resolution": "1280x720",
                    "latency": {"mean_ms": 10, "p50_ms": 9, "p95_ms": 15, "p99_ms": 20},
                    "throughput": {"items_per_second": 100},
                }
            }
        }
        latex = generate_throughput_table(data)
        assert "\\begin{table}" in latex
        assert "1280x720" in latex
        assert "\\end{table}" in latex

    def test_tamper_table(self):
        from benchmarks.report.latex_table import generate_tamper_detection_table
        data = {
            "tamper_detection": {
                "phash": {"overall": {"tpr": 0.9, "fpr": 0.1, "precision": 0.9, "f1": 0.9, "accuracy": 0.9}},
            }
        }
        latex = generate_tamper_detection_table(data)
        assert "\\begin{table}" in latex
        assert "pHash" in latex
