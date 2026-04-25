"""
LaTeX 表格生成器。

从 benchmark JSON 结果生成论文可用的 LaTeX tabular 表格。
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Optional


def generate_throughput_table(data: dict) -> str:
    """生成吞吐量对比表格。"""
    rows = []
    throughput = data.get("throughput_by_resolution", {})

    for res_name, info in throughput.items():
        lat = info.get("latency", {})
        thr = info.get("throughput", {})
        rows.append(
            f"  {info.get('resolution', res_name)} & "
            f"{lat.get('mean_ms', 0):.1f} & "
            f"{lat.get('p50_ms', 0):.1f} & "
            f"{lat.get('p95_ms', 0):.1f} & "
            f"{lat.get('p99_ms', 0):.1f} & "
            f"{thr.get('items_per_second', 0):.1f} \\\\"
        )

    body = "\n".join(rows)
    return (
        "\\begin{table}[htbp]\n"
        "\\centering\n"
        "\\caption{GOP Processing Throughput by Resolution}\n"
        "\\label{tab:throughput}\n"
        "\\begin{tabular}{lrrrrr}\n"
        "\\toprule\n"
        "Resolution & Mean (ms) & P50 (ms) & P95 (ms) & P99 (ms) & GOP/s \\\\\n"
        "\\midrule\n"
        f"{body}\n"
        "\\bottomrule\n"
        "\\end{tabular}\n"
        "\\end{table}"
    )


def generate_tamper_detection_table(data: dict) -> str:
    """生成篡改检测准确率表格。"""
    rows = []
    detection = data.get("tamper_detection", {})

    for method_name, method_data in detection.items():
        overall = method_data.get("overall", {})
        if not overall:
            continue

        display_name = {
            "naive_sha256": "SHA-256 Only",
            "phash": "pHash",
            "vif_fusion": "VIF (Ours)",
        }.get(method_name, method_name)

        rows.append(
            f"  {display_name} & "
            f"{overall.get('tpr', 0):.3f} & "
            f"{overall.get('fpr', 0):.3f} & "
            f"{overall.get('precision', 0):.3f} & "
            f"{overall.get('f1', 0):.3f} & "
            f"{overall.get('accuracy', 0):.3f} \\\\"
        )

    body = "\n".join(rows)
    return (
        "\\begin{table}[htbp]\n"
        "\\centering\n"
        "\\caption{Tamper Detection Performance Comparison}\n"
        "\\label{tab:tamper_detection}\n"
        "\\begin{tabular}{lrrrrr}\n"
        "\\toprule\n"
        "Method & TPR & FPR & Precision & F1 & Accuracy \\\\\n"
        "\\midrule\n"
        f"{body}\n"
        "\\bottomrule\n"
        "\\end{tabular}\n"
        "\\end{table}"
    )


def generate_latency_table(data: dict) -> str:
    """生成延迟分解表格。"""
    rows = []
    breakdown = data.get("latency_breakdown", {})

    for stage, stats in breakdown.items():
        display = {
            "sha256": "SHA-256",
            "phash": "Perceptual Hash",
            "merkle_leaf": "Merkle Leaf Hash",
            "total": "\\textbf{Total}",
        }.get(stage, stage)

        rows.append(
            f"  {display} & "
            f"{stats.get('mean_ms', 0):.2f} & "
            f"{stats.get('std_ms', 0):.2f} & "
            f"{stats.get('p50_ms', 0):.2f} & "
            f"{stats.get('p95_ms', 0):.2f} \\\\"
        )

    body = "\n".join(rows)
    return (
        "\\begin{table}[htbp]\n"
        "\\centering\n"
        "\\caption{Per-GOP Latency Breakdown (720p)}\n"
        "\\label{tab:latency}\n"
        "\\begin{tabular}{lrrrr}\n"
        "\\toprule\n"
        "Stage & Mean (ms) & Std (ms) & P50 (ms) & P95 (ms) \\\\\n"
        "\\midrule\n"
        f"{body}\n"
        "\\bottomrule\n"
        "\\end{tabular}\n"
        "\\end{table}"
    )


def generate_all_tables(results: dict) -> str:
    """从完整结果生成所有表格。"""
    tables = []
    scenarios = results.get("scenarios", {})

    if "throughput" in scenarios:
        tables.append(generate_throughput_table(scenarios["throughput"]))
    if "latency" in scenarios:
        tables.append(generate_latency_table(scenarios["latency"]))
    if "tamper_detection" in scenarios:
        tables.append(generate_tamper_detection_table(scenarios["tamper_detection"]))

    return "\n\n".join(tables)


def main():
    parser = argparse.ArgumentParser(description="Generate LaTeX tables from results")
    parser.add_argument("--input", required=True, help="JSON results file path")
    parser.add_argument("--output", default=None, help="Output .tex file path")
    args = parser.parse_args()

    with open(args.input) as f:
        results = json.load(f)

    latex = generate_all_tables(results)

    if args.output:
        with open(args.output, "w") as f:
            f.write(latex)
        print(f"LaTeX tables saved to {args.output}")
    else:
        print(latex)


if __name__ == "__main__":
    main()
