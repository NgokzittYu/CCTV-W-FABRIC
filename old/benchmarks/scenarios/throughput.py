"""
场景：吞吐量测试。

测量不同分辨率下 GOP 处理速度（哈希计算 + 指纹提取 + Merkle 树构建）。
"""

import logging
from typing import Any, Dict

from benchmarks.config import BenchmarkConfig
from benchmarks.datasets import generate_gop
from benchmarks.metrics import LatencyStats, ThroughputStats, measure_time

logger = logging.getLogger(__name__)


def run(config: BenchmarkConfig) -> Dict[str, Any]:
    """运行吞吐量场景。"""
    results = {}

    for res_name, (w, h) in config.resolutions.items():
        logger.info(f"  Testing resolution: {res_name} ({w}x{h})")
        latency = LatencyStats()
        throughput = ThroughputStats()

        # Warmup
        for i in range(config.warmup_rounds):
            gop = generate_gop(i, w, h, config.frames_per_gop)
            _process_gop(gop)

        # 正式测试
        for round_idx in range(config.rounds):
            round_latency = LatencyStats()

            with measure_time() as t:
                for gop_idx in range(config.gops_per_round):
                    gop = generate_gop(gop_idx, w, h, config.frames_per_gop)
                    with measure_time() as gop_t:
                        _process_gop(gop)
                    round_latency.add(gop_t["elapsed_ms"])
                    latency.add(gop_t["elapsed_ms"])

            throughput.total_items += config.gops_per_round
            throughput.total_seconds += t["elapsed_ms"] / 1000

        results[res_name] = {
            "resolution": f"{w}x{h}",
            "latency": latency.to_dict(),
            "throughput": throughput.to_dict(),
        }

        logger.info(
            f"    {res_name}: {throughput.items_per_second:.1f} GOP/s, "
            f"P50={latency.p50:.1f}ms, P95={latency.p95:.1f}ms"
        )

    return {"throughput_by_resolution": results}


def _process_gop(gop):
    """处理单个 GOP：哈希 + 指纹 + Merkle。"""
    import hashlib
    from services.perceptual_hash import compute_phash
    from services.merkle_utils import compute_leaf_hash

    # 密码学哈希
    _ = gop.sha256_hash

    # 感知哈希
    phash = compute_phash(gop.keyframe)

    # Merkle 叶子哈希
    compute_leaf_hash(gop.sha256_hash, phash=phash)
