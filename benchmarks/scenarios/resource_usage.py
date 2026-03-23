"""
场景：资源使用测试。

测量各模块运行时的 CPU 和内存占用。
"""

import logging
from typing import Any, Dict

from benchmarks.config import BenchmarkConfig
from benchmarks.datasets import generate_gop
from benchmarks.metrics import ResourceSnapshot, measure_time

logger = logging.getLogger(__name__)


def run(config: BenchmarkConfig) -> Dict[str, Any]:
    """运行资源使用场景。"""
    w, h = config.resolutions.get("720p", (1280, 720))
    num_gops = min(20, config.gops_per_round)

    # 基线快照
    baseline = ResourceSnapshot.capture()

    stages = {}
    for stage_name, process_fn in [
        ("sha256", _run_sha256),
        ("phash", _run_phash),
        ("merkle_build", _run_merkle),
        ("full_pipeline", _run_full_pipeline),
    ]:
        before = ResourceSnapshot.capture()
        with measure_time() as t:
            process_fn(w, h, num_gops)
        after = ResourceSnapshot.capture()

        stages[stage_name] = {
            "elapsed_ms": round(t["elapsed_ms"], 2),
            "cpu_before": before.cpu_percent,
            "cpu_after": after.cpu_percent,
            "memory_before_mb": round(before.memory_mb, 1),
            "memory_after_mb": round(after.memory_mb, 1),
            "memory_delta_mb": round(after.memory_mb - before.memory_mb, 1),
        }

        logger.info(
            f"  {stage_name}: {t['elapsed_ms']:.0f}ms, "
            f"mem={after.memory_mb:.0f}MB (+{after.memory_mb - before.memory_mb:.1f}MB)"
        )

    return {
        "resource_usage": {
            "baseline": baseline.to_dict(),
            "stages": stages,
            "num_gops": num_gops,
            "resolution": f"{w}x{h}",
        }
    }


def _run_sha256(w, h, n):
    import hashlib
    for i in range(n):
        gop = generate_gop(i, w, h, 15)
        hashlib.sha256(gop.keyframe.tobytes()).hexdigest()


def _run_phash(w, h, n):
    from services.perceptual_hash import compute_phash
    for i in range(n):
        gop = generate_gop(i, w, h, 15)
        compute_phash(gop.keyframe)


def _run_merkle(w, h, n):
    from services.merkle_utils import compute_leaf_hash
    for i in range(n):
        gop = generate_gop(i, w, h, 15)
        compute_leaf_hash(gop.sha256_hash)


def _run_full_pipeline(w, h, n):
    import hashlib
    from services.perceptual_hash import compute_phash
    from services.merkle_utils import compute_leaf_hash
    for i in range(n):
        gop = generate_gop(i, w, h, 15)
        sha = hashlib.sha256(gop.keyframe.tobytes()).hexdigest()
        phash = compute_phash(gop.keyframe)
        compute_leaf_hash(sha, phash=phash)
