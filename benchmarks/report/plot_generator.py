"""
论文图表生成器。

使用 matplotlib + seaborn 生成论文级图表。
"""

import argparse
import json
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")  # 非交互模式
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np


# 论文风格设置
def _setup_style():
    sns.set_theme(style="whitegrid", font_scale=1.2)
    plt.rcParams.update({
        "figure.figsize": (8, 5),
        "figure.dpi": 300,
        "font.size": 12,
        "axes.labelsize": 13,
        "axes.titlesize": 14,
        "xtick.labelsize": 11,
        "ytick.labelsize": 11,
        "legend.fontsize": 11,
    })


def plot_throughput_bar(data: dict, output_dir: Path, fmt: str = "pdf"):
    """吞吐量柱状图。"""
    _setup_style()
    throughput = data.get("throughput_by_resolution", {})

    resolutions = []
    gops_per_sec = []
    p95_latency = []

    for name, info in throughput.items():
        resolutions.append(info.get("resolution", name))
        gops_per_sec.append(info["throughput"]["items_per_second"])
        p95_latency.append(info["latency"]["p95_ms"])

    fig, ax1 = plt.subplots()

    x = np.arange(len(resolutions))
    bars = ax1.bar(x, gops_per_sec, 0.5, color=sns.color_palette("Blues_d", len(resolutions)))
    ax1.set_xlabel("Resolution")
    ax1.set_ylabel("Throughput (GOP/s)")
    ax1.set_xticks(x)
    ax1.set_xticklabels(resolutions)
    ax1.set_title("GOP Processing Throughput")

    # 在柱子上标注数值
    for bar, val in zip(bars, gops_per_sec):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                 f"{val:.1f}", ha="center", va="bottom", fontsize=10)

    plt.tight_layout()
    path = output_dir / f"throughput.{fmt}"
    plt.savefig(path, bbox_inches="tight")
    plt.close()
    return path


def plot_latency_breakdown(data: dict, output_dir: Path, fmt: str = "pdf"):
    """延迟分解堆积柱状图。"""
    _setup_style()
    breakdown = data.get("latency_breakdown", {})

    stages = [k for k in breakdown if k != "total"]
    means = [breakdown[s]["mean_ms"] for s in stages]

    labels = {
        "sha256": "SHA-256",
        "phash": "pHash",
        "merkle_leaf": "Merkle",
    }

    fig, ax = plt.subplots(figsize=(6, 4))
    colors = sns.color_palette("Set2", len(stages))
    ax.barh([labels.get(s, s) for s in stages], means, color=colors)

    for i, (s, v) in enumerate(zip(stages, means)):
        ax.text(v + 0.1, i, f"{v:.1f}ms", va="center", fontsize=10)

    ax.set_xlabel("Latency (ms)")
    ax.set_title("Per-GOP Latency Breakdown (720p)")
    plt.tight_layout()
    path = output_dir / f"latency_breakdown.{fmt}"
    plt.savefig(path, bbox_inches="tight")
    plt.close()
    return path


def plot_tamper_detection_comparison(data: dict, output_dir: Path, fmt: str = "pdf"):
    """篡改检测方法对比柱状图。"""
    _setup_style()
    detection = data.get("tamper_detection", {})

    methods = []
    f1_scores = []
    tpr_scores = []

    display = {"naive_sha256": "SHA-256", "phash": "pHash", "vif_fusion": "VIF (Ours)"}

    for method, results in detection.items():
        overall = results.get("overall", {})
        if not overall:
            continue
        methods.append(display.get(method, method))
        f1_scores.append(overall.get("f1", 0))
        tpr_scores.append(overall.get("tpr", 0))

    x = np.arange(len(methods))
    width = 0.35

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.bar(x - width/2, tpr_scores, width, label="TPR (Recall)", color=sns.color_palette()[0])
    ax.bar(x + width/2, f1_scores, width, label="F1 Score", color=sns.color_palette()[2])

    ax.set_xticks(x)
    ax.set_xticklabels(methods)
    ax.set_ylabel("Score")
    ax.set_title("Tamper Detection: Method Comparison")
    ax.legend()
    ax.set_ylim(0, 1.1)

    plt.tight_layout()
    path = output_dir / f"tamper_comparison.{fmt}"
    plt.savefig(path, bbox_inches="tight")
    plt.close()
    return path


def plot_scalability(data: dict, output_dir: Path, fmt: str = "pdf"):
    """并发可扩展性折线图。"""
    _setup_style()
    scalability = data.get("scalability", {})

    devices = []
    throughputs = []

    for key, info in sorted(scalability.items()):
        devices.append(info["num_devices"])
        throughputs.append(info["throughput"]["items_per_second"])

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(devices, throughputs, "o-", linewidth=2, markersize=8, color=sns.color_palette()[0])

    # 理想线性扩展
    if throughputs:
        ideal = [throughputs[0] * d / devices[0] for d in devices]
        ax.plot(devices, ideal, "--", color="gray", alpha=0.5, label="Ideal linear")

    ax.set_xlabel("Number of Concurrent Devices")
    ax.set_ylabel("Total Throughput (GOP/s)")
    ax.set_title("Scalability: Throughput vs. Concurrency")
    ax.legend()
    plt.tight_layout()
    path = output_dir / f"scalability.{fmt}"
    plt.savefig(path, bbox_inches="tight")
    plt.close()
    return path


def generate_all_plots(results: dict, output_dir: Path, fmt: str = "pdf"):
    """生成所有图表。"""
    output_dir.mkdir(parents=True, exist_ok=True)
    scenarios = results.get("scenarios", {})
    paths = []

    if "throughput" in scenarios:
        paths.append(plot_throughput_bar(scenarios["throughput"], output_dir, fmt))
    if "latency" in scenarios:
        paths.append(plot_latency_breakdown(scenarios["latency"], output_dir, fmt))
    if "tamper_detection" in scenarios:
        paths.append(plot_tamper_detection_comparison(scenarios["tamper_detection"], output_dir, fmt))
    if "scalability" in scenarios:
        paths.append(plot_scalability(scenarios["scalability"], output_dir, fmt))

    return paths


def main():
    parser = argparse.ArgumentParser(description="Generate benchmark plots")
    parser.add_argument("--input", required=True, help="JSON results file")
    parser.add_argument("--output", default="benchmark_results", help="Output dir")
    parser.add_argument("--format", default="pdf", choices=["pdf", "png", "svg"])
    args = parser.parse_args()

    with open(args.input) as f:
        results = json.load(f)

    paths = generate_all_plots(results, Path(args.output), args.format)
    for p in paths:
        print(f"  Generated: {p}")


if __name__ == "__main__":
    main()
