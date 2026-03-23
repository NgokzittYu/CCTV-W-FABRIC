"""
场景：并发可扩展性测试。

模拟多设备并发 GOP 处理，测量吞吐量随设备数的变化。
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

from benchmarks.config import BenchmarkConfig
from benchmarks.datasets import generate_gop
from benchmarks.metrics import ThroughputStats, measure_time

logger = logging.getLogger(__name__)


def run(config: BenchmarkConfig) -> Dict[str, Any]:
    """运行并发可扩展性场景。"""
    w, h = config.resolutions.get("720p", (1280, 720))
    gops_per_device = max(10, config.gops_per_round // 5)
    results = {}

    for num_devices in config.concurrency_levels:
        logger.info(f"  Testing concurrency: {num_devices} devices")
        throughput = ThroughputStats()

        with measure_time() as t:
            with ThreadPoolExecutor(max_workers=num_devices) as executor:
                futures = []
                for dev_id in range(num_devices):
                    futures.append(
                        executor.submit(_device_workload, dev_id, w, h, gops_per_device)
                    )
                for f in futures:
                    f.result()

        throughput.total_items = num_devices * gops_per_device
        throughput.total_seconds = t["elapsed_ms"] / 1000

        results[f"{num_devices}_devices"] = {
            "num_devices": num_devices,
            "gops_per_device": gops_per_device,
            "total_gops": throughput.total_items,
            "throughput": throughput.to_dict(),
        }

        logger.info(
            f"    {num_devices} devices: {throughput.items_per_second:.1f} GOP/s total"
        )

    return {"scalability": results}


def _device_workload(device_id: int, w: int, h: int, num_gops: int):
    """单设备工作负载。"""
    import hashlib
    from services.perceptual_hash import compute_phash

    for i in range(num_gops):
        gop = generate_gop(device_id * 10000 + i, w, h, num_frames=15)
        _ = hashlib.sha256(gop.keyframe.tobytes()).hexdigest()
        compute_phash(gop.keyframe)
