#!/usr/bin/env python3
import argparse
import copy
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from rich.console import Console
from rich.table import Table
from tabulate import tabulate

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.gop_splitter import split_gops
from services.perceptual_hash import compute_phash, hamming_distance

console = Console()
RESULTS_DIR = PROJECT_ROOT / "results" / "ablation_phash"


def _check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _compute_hashes(mode: str, gops) -> list[str | None]:
    previous = os.environ.get("PHASH_MODE")
    os.environ["PHASH_MODE"] = mode
    try:
        return [compute_phash(gop.keyframe_frame) for gop in gops]
    finally:
        if previous is None:
            os.environ.pop("PHASH_MODE", None)
        else:
            os.environ["PHASH_MODE"] = previous


def _match_gops_by_time(original_gops, other_gops):
    pairs = []
    for original in original_gops:
        matched = min(other_gops, key=lambda candidate: abs(candidate.start_time - original.start_time))
        pairs.append((original, matched))
    return pairs


def _distance_pairs(left_hashes, right_hashes) -> list[int]:
    distances = []
    for left, right in zip(left_hashes, right_hashes):
        if left is None or right is None:
            continue
        distances.append(hamming_distance(left, right))
    return distances


def _summarize(distances: list[int]) -> dict[str, float]:
    if not distances:
        return {"count": 0, "mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0}

    array = np.asarray(distances, dtype=np.float32)
    return {
        "count": int(array.size),
        "mean": float(array.mean()),
        "std": float(array.std()),
        "min": float(array.min()),
        "max": float(array.max()),
    }


def _transcode_video(video_path: Path, output_path: Path):
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-c:v",
            "libx264",
            "-b:v",
            "500k",
            "-g",
            "30",
            "-keyint_min",
            "30",
            "-sc_threshold",
            "0",
            "-forced-idr",
            "1",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ],
        check=True,
        capture_output=True,
    )


def _build_tampered_gops(gops):
    tampered = copy.deepcopy(gops)
    if len(tampered) < 2:
        return tampered

    source_index = len(tampered) - 1
    target_index = len(tampered) // 2
    tampered[target_index].keyframe_frame = tampered[source_index].keyframe_frame.copy()
    return tampered


def _collect_scenario_distances(original_gops, reencoded_gops):
    original_legacy = _compute_hashes("legacy", original_gops)
    original_deep = _compute_hashes("deep", original_gops)

    intact = {
        "legacy": _distance_pairs(original_legacy, original_legacy),
        "deep": _distance_pairs(original_deep, original_deep),
    }

    pairs = _match_gops_by_time(original_gops, reencoded_gops)
    reencoded_legacy_left = _compute_hashes("legacy", [left for left, _ in pairs])
    reencoded_legacy_right = _compute_hashes("legacy", [right for _, right in pairs])
    reencoded_deep_left = _compute_hashes("deep", [left for left, _ in pairs])
    reencoded_deep_right = _compute_hashes("deep", [right for _, right in pairs])
    reencoded = {
        "legacy": _distance_pairs(reencoded_legacy_left, reencoded_legacy_right),
        "deep": _distance_pairs(reencoded_deep_left, reencoded_deep_right),
    }

    tampered_gops = _build_tampered_gops(original_gops)
    tampered_legacy = _compute_hashes("legacy", tampered_gops)
    tampered_deep = _compute_hashes("deep", tampered_gops)
    tampered = {
        "legacy": _distance_pairs(original_legacy, tampered_legacy),
        "deep": _distance_pairs(original_deep, tampered_deep),
    }

    return {
        "INTACT": intact,
        "RE_ENCODED": reencoded,
        "TAMPERED": tampered,
    }


def _print_summary(video_path: Path, scenario_distances):
    rich_table = Table(title=f"pHash 消融统计: {video_path.name}")
    rich_table.add_column("Scenario")
    rich_table.add_column("Mode")
    rich_table.add_column("Count", justify="right")
    rich_table.add_column("Mean", justify="right")
    rich_table.add_column("Std", justify="right")
    rich_table.add_column("Min", justify="right")
    rich_table.add_column("Max", justify="right")

    plain_rows = []
    for scenario, modes in scenario_distances.items():
        for mode, distances in modes.items():
            stats = _summarize(distances)
            rich_table.add_row(
                scenario,
                mode,
                str(stats["count"]),
                f"{stats['mean']:.2f}",
                f"{stats['std']:.2f}",
                f"{stats['min']:.2f}",
                f"{stats['max']:.2f}",
            )
            plain_rows.append([
                scenario,
                mode,
                stats["count"],
                f"{stats['mean']:.2f}",
                f"{stats['std']:.2f}",
                f"{stats['min']:.2f}",
                f"{stats['max']:.2f}",
            ])

    console.print(rich_table)
    print(tabulate(plain_rows, headers=["scenario", "mode", "count", "mean", "std", "min", "max"], tablefmt="github"))


def _plot_results(video_name: str, scenario_distances):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    scenarios = list(scenario_distances.keys())
    legacy_means = [_summarize(scenario_distances[scenario]["legacy"])["mean"] for scenario in scenarios]
    deep_means = [_summarize(scenario_distances[scenario]["deep"])["mean"] for scenario in scenarios]

    x = np.arange(len(scenarios))
    width = 0.35

    fig, axes = plt.subplots(1, 2, figsize=(13, 5))

    axes[0].bar(x - width / 2, legacy_means, width, label="legacy")
    axes[0].bar(x + width / 2, deep_means, width, label="deep")
    axes[0].set_title("Average Hamming Distance")
    axes[0].set_xticks(x)
    axes[0].set_xticklabels(scenarios)
    axes[0].set_ylabel("Distance")
    axes[0].legend()

    box_data = []
    box_labels = []
    for scenario in scenarios:
        box_data.append(scenario_distances[scenario]["legacy"] or [0])
        box_labels.append(f"{scenario}\nlegacy")
        box_data.append(scenario_distances[scenario]["deep"] or [0])
        box_labels.append(f"{scenario}\ndeep")

    axes[1].boxplot(box_data, labels=box_labels)
    axes[1].set_title("Hamming Distance Distribution")
    axes[1].set_ylabel("Distance")
    axes[1].tick_params(axis="x", rotation=25)

    fig.suptitle(f"pHash Ablation - {video_name}")
    fig.tight_layout()

    output_path = RESULTS_DIR / f"{Path(video_name).stem}_ablation.png"
    fig.savefig(output_path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    console.print(f"[green]Saved plot:[/green] {output_path}")


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


def run_ablation(video_path: Path):
    if not _check_ffmpeg():
        raise RuntimeError("ffmpeg is required for re-encoding ablation")

    with tempfile.TemporaryDirectory(prefix="ablation_phash_") as tmp_dir:
        reencoded_path = Path(tmp_dir) / f"{video_path.stem}_reencoded.mp4"
        console.print(f"[cyan]Splitting original video:[/cyan] {video_path}")
        original_gops = split_gops(str(video_path))
        console.print(f"[cyan]Original GOP count:[/cyan] {len(original_gops)}")

        console.print(f"[cyan]Transcoding video:[/cyan] {video_path.name}")
        _transcode_video(video_path, reencoded_path)
        reencoded_gops = split_gops(str(reencoded_path))
        console.print(f"[cyan]Re-encoded GOP count:[/cyan] {len(reencoded_gops)}")

        scenario_distances = _collect_scenario_distances(original_gops, reencoded_gops)
        _print_summary(video_path, scenario_distances)
        _plot_results(video_path.name, scenario_distances)


def main():
    parser = argparse.ArgumentParser(description="Ablation study for legacy vs deep perceptual hash")
    parser.add_argument("--video", type=str, default=None, help="single mp4 video path")
    parser.add_argument("--video-dir", type=str, default=None, help="directory containing mp4 videos")
    args = parser.parse_args()

    videos = _resolve_videos(args.video, args.video_dir)
    for video_path in videos:
        run_ablation(video_path)


if __name__ == "__main__":
    main()
