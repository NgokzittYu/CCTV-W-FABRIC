"""
Benchmark 配置管理。

定义分辨率、轮次、warmup 等参数。
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass
class BenchmarkConfig:
    """Benchmark 全局配置。"""

    # 测试轮次
    rounds: int = 3
    warmup_rounds: int = 1

    # 分辨率配置 (name -> (width, height))
    resolutions: Dict[str, Tuple[int, int]] = field(default_factory=lambda: {
        "480p": (854, 480),
        "720p": (1280, 720),
        "1080p": (1920, 1080),
    })

    # GOP 配置
    gops_per_round: int = 50
    frames_per_gop: int = 15

    # 并发设备数
    concurrency_levels: List[int] = field(default_factory=lambda: [1, 5, 10, 20])

    # 篡改检测场景
    tamper_types: List[str] = field(default_factory=lambda: [
        "frame_replace",   # 帧替换
        "content_overlay",  # 内容叠加
        "temporal_shift",   # 时间偏移
        "compression",      # 重压缩
        "noise_inject",     # 噪声注入
    ])

    # 输出配置
    output_dir: Path = Path("benchmark_results")
    results_file: str = "results.json"

    # 图表配置
    fig_dpi: int = 300
    fig_format: str = "pdf"
    font_size: int = 12

    def __post_init__(self):
        self.output_dir = Path(self.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def results_path(self) -> Path:
        return self.output_dir / self.results_file
