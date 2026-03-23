"""
场景：延迟分解测试。

测量单 GOP 处理中各子模块的延迟分布。
"""

import logging
from typing import Any, Dict

from benchmarks.config import BenchmarkConfig
from benchmarks.datasets import generate_gop
from benchmarks.metrics import LatencyStats, measure_time

logger = logging.getLogger(__name__)


def run(config: BenchmarkConfig) -> Dict[str, Any]:
    """运行延迟分解场景。"""
    w, h = config.resolutions.get("720p", (1280, 720))
    num_gops = config.gops_per_round

    stages = {
        "sha256": LatencyStats(),
        "phash": LatencyStats(),
        "merkle_leaf": LatencyStats(),
        "total": LatencyStats(),
    }

    # Warmup
    for i in range(config.warmup_rounds * 5):
        gop = generate_gop(i, w, h, config.frames_per_gop)
        _process_gop_with_timing(gop)

    # 正式测试
    for round_idx in range(config.rounds):
        for gop_idx in range(num_gops):
            gop = generate_gop(gop_idx + round_idx * num_gops, w, h, config.frames_per_gop)
            timings = _process_gop_with_timing(gop)
            for stage, ms in timings.items():
                stages[stage].add(ms)

    result = {}
    for stage, stats in stages.items():
        result[stage] = stats.to_dict()
        logger.info(f"  {stage}: mean={stats.mean:.2f}ms, P95={stats.p95:.2f}ms")

    return {"latency_breakdown": result}


def _process_gop_with_timing(gop) -> Dict[str, float]:
    """处理 GOP 并返回各阶段耗时。"""
    import hashlib
    from services.perceptual_hash import compute_phash
    from services.merkle_utils import compute_leaf_hash

    timings = {}

    with measure_time() as total_t:
        with measure_time() as t:
            _ = hashlib.sha256(gop.keyframe.tobytes()).hexdigest()
        timings["sha256"] = t["elapsed_ms"]

        with measure_time() as t:
            phash = compute_phash(gop.keyframe)
        timings["phash"] = t["elapsed_ms"]

        with measure_time() as t:
            compute_leaf_hash(gop.sha256_hash, phash=phash)
        timings["merkle_leaf"] = t["elapsed_ms"]

    timings["total"] = total_t["elapsed_ms"]
    return timings
