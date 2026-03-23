#!/usr/bin/env python3
"""
EIS 消融实验 — lite vs full 模式对比

用于论文和答辩的 EIS 多信号融合消融实验：
  1. 用 gop_splitter 切分视频为 GOP
  2. 对每个 GOP 同时运行 lite 和 full EIS
  3. 绘制对比图（折线图、面积图、状态时间线）
  4. 统计输出（时间占比、切换时刻、上报频率）
  5. 保存图片到 results/ablation_eis/

Usage:
    python scripts/ablation_eis.py --video "video.mp4"
    python scripts/ablation_eis.py --video-dir sample_videos/
"""

import argparse
import os
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from rich.console import Console
from rich.table import Table
from tabulate import tabulate

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.adaptive_anchor import AdaptiveAnchor
from services.gop_splitter import split_gops

console = Console()
RESULTS_DIR = PROJECT_ROOT / "results" / "ablation_eis"


# ---------------------------------------------------------------------------
# Core experiment
# ---------------------------------------------------------------------------

def _run_eis(gops, mode: str) -> list[dict]:
    """Run EIS on a list of GOPs in the given mode and return per-GOP results."""
    anchor = AdaptiveAnchor(eis_mode=mode)
    results = []
    for gop in gops:
        if gop.semantic_fingerprint is None:
            continue

        decision = anchor.update(
            gop.semantic_fingerprint,
            keyframe=gop.keyframe_frame if mode == "full" else None,
        )

        entry = {
            "gop_id": gop.gop_id,
            "time": gop.start_time,
            "eis_score": decision.eis_score,
            "level": decision.level,
            "interval": decision.report_interval_seconds,
            "should_report": decision.should_report_now,
        }

        if decision.signal_breakdown:
            entry["obj_signal"] = decision.signal_breakdown.get("object", 0)
            entry["motion_signal"] = decision.signal_breakdown.get("motion", 0)
            entry["anomaly_signal"] = decision.signal_breakdown.get("anomaly", 0)

        results.append(entry)

    return results


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------

def _level_time_ratio(results: list[dict]) -> dict[str, float]:
    """Calculate fraction of GOPs spent in each level."""
    if not results:
        return {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    for r in results:
        counts[r["level"]] = counts.get(r["level"], 0) + 1
    total = len(results)
    return {k: round(v / total, 4) for k, v in counts.items()}


def _transition_points(results: list[dict]) -> list[int]:
    """Return GOP IDs where level changed."""
    transitions = []
    for i in range(1, len(results)):
        if results[i]["level"] != results[i - 1]["level"]:
            transitions.append(results[i]["gop_id"])
    return transitions


def _avg_report_interval(results: list[dict]) -> float:
    """Average report interval across all GOPs."""
    if not results:
        return 0
    return sum(r["interval"] for r in results) / len(results)


# ---------------------------------------------------------------------------
# Plots
# ---------------------------------------------------------------------------

_LEVEL_COLORS = {"LOW": "#4CAF50", "MEDIUM": "#FF9800", "HIGH": "#F44336"}
_LEVEL_Y = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def _plot_dual_eis(lite_results, full_results, video_name: str, save_dir: Path):
    """Plot 1: dual line chart — lite EIS vs full EIS over time."""
    fig, ax = plt.subplots(figsize=(12, 4))

    times_lite = [r["time"] for r in lite_results]
    eis_lite = [r["eis_score"] for r in lite_results]
    times_full = [r["time"] for r in full_results]
    eis_full = [r["eis_score"] for r in full_results]

    ax.plot(times_lite, eis_lite, label="Lite EIS", linewidth=1.5, alpha=0.8, color="#2196F3")
    ax.plot(times_full, eis_full, label="Full EIS", linewidth=1.5, alpha=0.8, color="#E91E63")

    ax.axhline(y=0.3, color="gray", linestyle="--", linewidth=0.8, alpha=0.5, label="LOW/MEDIUM threshold")
    ax.axhline(y=0.7, color="gray", linestyle="-.", linewidth=0.8, alpha=0.5, label="MEDIUM/HIGH threshold")

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("EIS Score")
    ax.set_title(f"EIS Comparison — {video_name}")
    ax.set_ylim(-0.05, 1.05)
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    path = save_dir / f"{Path(video_name).stem}_eis_comparison.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    console.print(f"[green]Saved:[/green] {path}")


def _plot_signal_stack(full_results, video_name: str, save_dir: Path):
    """Plot 2: stacked area chart of signal components (full mode only)."""
    if not full_results or "obj_signal" not in full_results[0]:
        console.print("[yellow]Skipping signal stack plot (no signal breakdown).[/yellow]")
        return

    fig, ax = plt.subplots(figsize=(12, 4))

    times = [r["time"] for r in full_results]
    obj = [r.get("obj_signal", 0) for r in full_results]
    mot = [r.get("motion_signal", 0) for r in full_results]
    ano = [r.get("anomaly_signal", 0) for r in full_results]

    ax.stackplot(
        times, obj, mot, ano,
        labels=["Object Signal", "Motion Signal", "Anomaly Signal"],
        colors=["#42A5F5", "#66BB6A", "#EF5350"],
        alpha=0.75,
    )

    ax.set_xlabel("Time (s)")
    ax.set_ylabel("Signal Value")
    ax.set_title(f"Signal Breakdown (Full EIS) — {video_name}")
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    path = save_dir / f"{Path(video_name).stem}_signal_stack.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    console.print(f"[green]Saved:[/green] {path}")


def _plot_state_timeline(lite_results, full_results, video_name: str, save_dir: Path):
    """Plot 3: state transition timeline (horizontal bar)."""
    fig, axes = plt.subplots(2, 1, figsize=(12, 3), sharex=True)

    for ax, results, label in [(axes[0], lite_results, "Lite"), (axes[1], full_results, "Full")]:
        for i, r in enumerate(results):
            t_start = r["time"]
            t_end = results[i + 1]["time"] if i + 1 < len(results) else t_start + 1
            color = _LEVEL_COLORS.get(r["level"], "gray")
            ax.barh(0, t_end - t_start, left=t_start, height=0.6, color=color, edgecolor="none")

        ax.set_yticks([0])
        ax.set_yticklabels([label])
        ax.set_ylim(-0.5, 0.5)

    axes[1].set_xlabel("Time (s)")
    fig.suptitle(f"State Timeline — {video_name}", fontsize=11)

    # Legend
    patches = [mpatches.Patch(color=c, label=l) for l, c in _LEVEL_COLORS.items()]
    fig.legend(handles=patches, loc="upper right", fontsize=8, ncol=3)

    fig.tight_layout()
    path = save_dir / f"{Path(video_name).stem}_state_timeline.png"
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    console.print(f"[green]Saved:[/green] {path}")


# ---------------------------------------------------------------------------
# Summary table
# ---------------------------------------------------------------------------

def _print_summary(video_name: str, lite_results, full_results):
    """Print statistics comparison table."""
    lite_ratio = _level_time_ratio(lite_results)
    full_ratio = _level_time_ratio(full_results)
    lite_trans = _transition_points(lite_results)
    full_trans = _transition_points(full_results)

    rich_table = Table(title=f"EIS 消融统计: {video_name}")
    rich_table.add_column("Metric")
    rich_table.add_column("Lite", justify="right")
    rich_table.add_column("Full", justify="right")

    rows = [
        ("GOP Count", str(len(lite_results)), str(len(full_results))),
        ("LOW %", f"{lite_ratio['LOW']:.2%}", f"{full_ratio['LOW']:.2%}"),
        ("MEDIUM %", f"{lite_ratio['MEDIUM']:.2%}", f"{full_ratio['MEDIUM']:.2%}"),
        ("HIGH %", f"{lite_ratio['HIGH']:.2%}", f"{full_ratio['HIGH']:.2%}"),
        ("Transitions", str(len(lite_trans)), str(len(full_trans))),
        ("Avg Interval (s)", f"{_avg_report_interval(lite_results):.1f}", f"{_avg_report_interval(full_results):.1f}"),
    ]

    plain_rows = []
    for metric, lite_val, full_val in rows:
        rich_table.add_row(metric, lite_val, full_val)
        plain_rows.append([metric, lite_val, full_val])

    console.print(rich_table)
    print(tabulate(plain_rows, headers=["Metric", "Lite", "Full"], tablefmt="github"))

    # Transition details
    if lite_trans or full_trans:
        console.print("\n[bold]Transition GOPs:[/bold]")
        console.print(f"  Lite: {lite_trans}")
        console.print(f"  Full: {full_trans}")

        # Compute lead/lag
        common_len = min(len(lite_trans), len(full_trans))
        if common_len > 0:
            leads = sum(1 for i in range(common_len) if full_trans[i] < lite_trans[i])
            lags = sum(1 for i in range(common_len) if full_trans[i] > lite_trans[i])
            console.print(f"  Full leads lite: {leads}, Full lags lite: {lags}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_ablation(video_path: Path):
    """Run ablation experiment on a single video."""
    console.rule(f"[bold cyan]EIS Ablation: {video_path.name}[/bold cyan]")

    console.print(f"[cyan]Splitting GOPs...[/cyan]")
    gops = split_gops(str(video_path))
    console.print(f"[cyan]Total GOPs:[/cyan] {len(gops)}")

    if not gops:
        console.print("[red]No GOPs found, skipping.[/red]")
        return

    # Run both modes
    console.print("[cyan]Running Lite EIS...[/cyan]")
    lite_results = _run_eis(gops, "lite")

    console.print("[cyan]Running Full EIS...[/cyan]")
    full_results = _run_eis(gops, "full")

    if not lite_results or not full_results:
        console.print("[red]No results (semantic fingerprints may be missing). Skipping.[/red]")
        return

    # Summary
    _print_summary(video_path.name, lite_results, full_results)

    # Plots
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _plot_dual_eis(lite_results, full_results, video_path.name, RESULTS_DIR)
    _plot_signal_stack(full_results, video_path.name, RESULTS_DIR)
    _plot_state_timeline(lite_results, full_results, video_path.name, RESULTS_DIR)

    console.print(f"\n[bold green]Results saved to {RESULTS_DIR}[/bold green]\n")


def _resolve_videos(video: str | None, video_dir: str | None) -> list[Path]:
    if video:
        path = Path(video).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(path)
        return [path]

    directory = Path(video_dir or PROJECT_ROOT / "sample_videos").expanduser().resolve()
    if not directory.exists():
        raise FileNotFoundError(directory)

    videos = sorted(directory.glob("*.mp4"))
    if not videos:
        raise FileNotFoundError(f"No mp4 files found in {directory}")
    return videos


def main():
    parser = argparse.ArgumentParser(description="Ablation study: EIS lite vs full")
    parser.add_argument("--video", type=str, default=None, help="Single video file path")
    parser.add_argument("--video-dir", type=str, default=None, help="Directory of mp4 videos")
    args = parser.parse_args()

    videos = _resolve_videos(args.video, args.video_dir)
    for video_path in videos:
        run_ablation(video_path)


if __name__ == "__main__":
    main()
