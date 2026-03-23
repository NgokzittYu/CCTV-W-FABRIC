"""
指标计算模块。

提供延迟百分位、吞吐量、分类指标（TPR/FPR/F1）和资源使用统计。
"""

import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import psutil


@dataclass
class LatencyStats:
    """延迟统计。"""
    values_ms: List[float] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.values_ms)

    @property
    def mean(self) -> float:
        return float(np.mean(self.values_ms)) if self.values_ms else 0.0

    @property
    def std(self) -> float:
        return float(np.std(self.values_ms)) if self.values_ms else 0.0

    @property
    def p50(self) -> float:
        return float(np.percentile(self.values_ms, 50)) if self.values_ms else 0.0

    @property
    def p95(self) -> float:
        return float(np.percentile(self.values_ms, 95)) if self.values_ms else 0.0

    @property
    def p99(self) -> float:
        return float(np.percentile(self.values_ms, 99)) if self.values_ms else 0.0

    @property
    def min(self) -> float:
        return float(np.min(self.values_ms)) if self.values_ms else 0.0

    @property
    def max(self) -> float:
        return float(np.max(self.values_ms)) if self.values_ms else 0.0

    def add(self, ms: float):
        self.values_ms.append(ms)

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "mean_ms": round(self.mean, 3),
            "std_ms": round(self.std, 3),
            "p50_ms": round(self.p50, 3),
            "p95_ms": round(self.p95, 3),
            "p99_ms": round(self.p99, 3),
            "min_ms": round(self.min, 3),
            "max_ms": round(self.max, 3),
        }


@dataclass
class ThroughputStats:
    """吞吐量统计。"""
    total_items: int = 0
    total_seconds: float = 0.0

    @property
    def items_per_second(self) -> float:
        return self.total_items / self.total_seconds if self.total_seconds > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "total_items": self.total_items,
            "total_seconds": round(self.total_seconds, 3),
            "items_per_second": round(self.items_per_second, 2),
        }


@dataclass
class ClassificationMetrics:
    """分类指标（篡改检测用）。"""
    tp: int = 0
    fp: int = 0
    tn: int = 0
    fn: int = 0

    @property
    def tpr(self) -> float:
        """True Positive Rate (Recall)."""
        return self.tp / (self.tp + self.fn) if (self.tp + self.fn) > 0 else 0.0

    @property
    def fpr(self) -> float:
        """False Positive Rate."""
        return self.fp / (self.fp + self.tn) if (self.fp + self.tn) > 0 else 0.0

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if (self.tp + self.fp) > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.tpr
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    @property
    def accuracy(self) -> float:
        total = self.tp + self.fp + self.tn + self.fn
        return (self.tp + self.tn) / total if total > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "tp": self.tp, "fp": self.fp, "tn": self.tn, "fn": self.fn,
            "tpr": round(self.tpr, 4),
            "fpr": round(self.fpr, 4),
            "precision": round(self.precision, 4),
            "f1": round(self.f1, 4),
            "accuracy": round(self.accuracy, 4),
        }


@dataclass
class ResourceSnapshot:
    """资源使用快照。"""
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    memory_percent: float = 0.0

    @staticmethod
    def capture() -> "ResourceSnapshot":
        proc = psutil.Process()
        mem = proc.memory_info()
        return ResourceSnapshot(
            cpu_percent=proc.cpu_percent(interval=0.1),
            memory_mb=mem.rss / (1024 * 1024),
            memory_percent=proc.memory_percent(),
        )

    def to_dict(self) -> dict:
        return {
            "cpu_percent": round(self.cpu_percent, 1),
            "memory_mb": round(self.memory_mb, 1),
            "memory_percent": round(self.memory_percent, 2),
        }


@contextmanager
def measure_time():
    """上下文管理器：测量执行时间（毫秒）。"""
    result = {"elapsed_ms": 0.0}
    start = time.perf_counter()
    try:
        yield result
    finally:
        result["elapsed_ms"] = (time.perf_counter() - start) * 1000
