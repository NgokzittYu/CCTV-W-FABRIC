"""
Benchmark 运行器。

支持多轮运行、warmup、结果收集和 JSON 持久化。
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from benchmarks.config import BenchmarkConfig

logger = logging.getLogger(__name__)


class BenchmarkRunner:
    """Benchmark 测试运行器。"""

    def __init__(self, config: Optional[BenchmarkConfig] = None):
        self.config = config or BenchmarkConfig()
        self.results: Dict[str, Any] = {
            "metadata": {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "rounds": self.config.rounds,
                "warmup_rounds": self.config.warmup_rounds,
            },
            "scenarios": {},
        }

    def run_scenario(
        self,
        name: str,
        scenario_fn: Callable[[BenchmarkConfig], Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        运行单个测试场景。

        Args:
            name: 场景名称
            scenario_fn: 场景函数，接收 config 返回结果字典

        Returns:
            场景结果
        """
        logger.info(f"=== Running scenario: {name} ===")
        start = time.time()

        result = scenario_fn(self.config)
        elapsed = time.time() - start

        result["_elapsed_seconds"] = round(elapsed, 2)
        self.results["scenarios"][name] = result

        logger.info(f"=== Scenario {name} completed in {elapsed:.1f}s ===")
        return result

    def run_all(
        self,
        scenarios: Optional[Dict[str, Callable]] = None,
    ) -> Dict[str, Any]:
        """运行所有场景。"""
        if scenarios is None:
            scenarios = self._get_default_scenarios()

        for name, fn in scenarios.items():
            self.run_scenario(name, fn)

        self.save_results()
        return self.results

    def save_results(self, path: Optional[Path] = None):
        """保存结果到 JSON。"""
        filepath = path or self.config.results_path
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, "w") as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)

        logger.info(f"Results saved to {filepath}")

    @staticmethod
    def _get_default_scenarios() -> Dict[str, Callable]:
        """获取默认场景。"""
        from benchmarks.scenarios.throughput import run as run_throughput
        from benchmarks.scenarios.latency import run as run_latency
        from benchmarks.scenarios.tamper_detection import run as run_tamper
        from benchmarks.scenarios.resource_usage import run as run_resource

        return {
            "throughput": run_throughput,
            "latency": run_latency,
            "tamper_detection": run_tamper,
            "resource_usage": run_resource,
        }


def main():
    """CLI 入口。"""
    parser = argparse.ArgumentParser(description="CCTV-W-FABRIC Benchmark Runner")
    parser.add_argument(
        "--scenario",
        choices=["throughput", "latency", "tamper_detection", "resource_usage", "all"],
        default="all",
        help="测试场景",
    )
    parser.add_argument("--rounds", type=int, default=3, help="测试轮次")
    parser.add_argument("--gops", type=int, default=50, help="每轮 GOP 数")
    parser.add_argument("--output", type=str, default="benchmark_results", help="输出目录")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

    config = BenchmarkConfig(
        rounds=args.rounds,
        gops_per_round=args.gops,
        output_dir=Path(args.output),
    )

    runner = BenchmarkRunner(config)

    if args.scenario == "all":
        runner.run_all()
    else:
        scenarios = runner._get_default_scenarios()
        if args.scenario in scenarios:
            runner.run_scenario(args.scenario, scenarios[args.scenario])
            runner.save_results()

    print(f"\n✅ Results saved to {config.results_path}")


if __name__ == "__main__":
    main()
