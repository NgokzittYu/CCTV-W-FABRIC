#!/usr/bin/env python3
"""
端到端篡改检测演示脚本

演示三种场景的完整流程：存证 → 篡改/转码 → 验证
- 场景 1: INTACT（完整）
- 场景 2: RE_ENCODED（转码未篡改）
- 场景 3: TAMPERED（已篡改 + 精确 GOP 定位）

Usage:
    python scripts/tamper_demo.py
    python scripts/tamper_demo.py --video path/to/video.mp4
    python scripts/tamper_demo.py --skip-ipfs --tamper-gop 3
"""
import argparse
import copy
import hashlib
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from services.gop_splitter import split_gops, GOPData
from services.tri_state_verifier import TriStateVerifier
from services.perceptual_hash import compute_phash, hamming_distance
from services.merkle_utils import (
    compute_leaf_hash,
    MerkleTree,
    HierarchicalMerkleTree,
)
from config import SETTINGS

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

console = Console()


@dataclass
class ScenarioResult:
    """场景执行结果，用于末尾汇总"""
    name: str
    total: int
    expected_count: int  # 符合预期的 GOP 数
    tampered_indices: Optional[list[int]] = None


def format_time(seconds: float) -> str:
    """将秒数格式化为 MM:SS.mmm"""
    m, s = divmod(seconds, 60)
    return f"{int(m):02d}:{s:06.3f}"


def check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def match_gops_by_time(original_gops, re_encoded_gops):
    """按时间戳最近邻匹配 GOP 对，带重复使用检测"""
    pairs = []
    used = set()
    for og in original_gops:
        best = min(re_encoded_gops, key=lambda rg: abs(rg.start_time - og.start_time))
        if id(best) in used:
            console.print(
                f"[yellow]   ⚠ GOP #{og.gop_id} 与前面的 GOP 共用了同一个转码 GOP "
                f"(start_time={best.start_time:.3f}s)[/yellow]"
            )
        used.add(id(best))
        pairs.append((og, best))
    return pairs


def ensure_test_video(video_path: str | None, tmp_dir: str) -> str:
    """返回可用的测试视频路径；无指定时用 FFmpeg 生成。"""
    if video_path:
        p = Path(video_path).expanduser().resolve()
        if not p.exists():
            console.print(f"[red]视频文件不存在: {p}[/red]")
            sys.exit(1)
        return str(p)

    if not check_ffmpeg():
        console.print("[red]未找到 ffmpeg，请安装或通过 --video 指定视频文件[/red]")
        sys.exit(1)

    out = Path(tmp_dir) / "test_input.mp4"
    console.print("[cyan]未指定视频，正在用 FFmpeg 生成 10 秒测试视频 ...[/cyan]")
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "testsrc2=duration=10:size=640x480:rate=25",
            "-c:v", "libx264", "-g", "30",
            "-pix_fmt", "yuv420p",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    console.print(f"[green]测试视频已生成: {out}[/green]\n")
    return str(out)


# ---------------------------------------------------------------------------
# 存证阶段（共用）
# ---------------------------------------------------------------------------

def register_video(
    video_path: str,
    skip_ipfs: bool,
    device_id: str = "demo_cam_001",
):
    """
    存证阶段：切分 → 哈希 → Merkle 树 → 可选 IPFS → 模拟上链

    Returns:
        (gops, merkle_tree, htree, segment_root)
    """
    console.print(Panel(
        "[bold]存证阶段[/bold]  视频切分 → 哈希计算 → Merkle 树 → 存储 → 模拟上链",
        style="blue",
    ))

    # 1) GOP 切分
    console.print("[cyan]① GOP 切分中 ...[/cyan]")
    t0 = time.time()
    gops = split_gops(video_path)
    elapsed = time.time() - t0
    console.print(f"   切分完成: {len(gops)} 个 GOP，耗时 {elapsed:.2f}s\n")

    if not gops:
        console.print("[red]未检测到任何 GOP，请检查视频文件[/red]")
        sys.exit(1)

    # 2) 展示 GOP 摘要
    tbl = Table(title="GOP 摘要", box=box.ROUNDED, show_lines=False)
    tbl.add_column("GOP#", justify="right", style="bold")
    tbl.add_column("时间范围", style="cyan")
    tbl.add_column("帧数", justify="right")
    tbl.add_column("大小", justify="right")
    tbl.add_column("SHA-256", style="dim")
    tbl.add_column("pHash", style="dim")
    for g in gops:
        tbl.add_row(
            str(g.gop_id),
            f"{format_time(g.start_time)} - {format_time(g.end_time)}",
            str(g.frame_count),
            f"{g.byte_size:,} B",
            g.sha256_hash[:16] + "...",
            g.phash or "N/A",
        )
    console.print(tbl)
    console.print()

    # 3) 构建 Merkle 树
    console.print("[cyan]② 构建 Merkle 树 ...[/cyan]")
    merkle_tree = MerkleTree(gops)
    console.print(f"   MerkleRoot = {merkle_tree.root[:32]}...")

    # 4) 构建分层 Merkle 树
    console.print("[cyan]③ 构建分层 Merkle 树 (HierarchicalMerkleTree) ...[/cyan]")
    htree = HierarchicalMerkleTree(chunk_duration=5.0, segment_duration=30.0)
    for g in gops:
        leaf = compute_leaf_hash(g.sha256_hash, g.phash, g.semantic_hash)
        htree.add_gop(leaf, g.start_time)
    segment_root = htree.close_segment()
    console.print(f"   SegmentRoot = {segment_root[:32]}...")

    # 5) IPFS 存储（可选）
    storage = None
    if not skip_ipfs:
        try:
            from services.ipfs_storage import VideoStorage
            console.print("[cyan]④ 上传 GOP 到 IPFS ...[/cyan]")
            storage = VideoStorage(
                api_url=SETTINGS.ipfs_api_url,
                gateway_url=SETTINGS.ipfs_gateway_url,
                pin_enabled=SETTINGS.ipfs_pin_enabled,
            )
            for g in gops:
                storage.upload_gop(device_id, g)
            console.print(f"   已上传 {len(gops)} 个 GOP 到 IPFS\n")
        except Exception as e:
            console.print(f"[yellow]   IPFS 不可用，跳过存储步骤: {e}[/yellow]\n")
    else:
        console.print("[dim]④ 跳过 IPFS 存储 (--skip-ipfs)[/dim]\n")

    # 6) 模拟上链
    console.print("[cyan]⑤ 模拟 Fabric 上链 ...[/cyan]")
    epoch_id = f"epoch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    console.print(f"   epoch_id     = {epoch_id}")
    console.print(f"   segment_root = {segment_root[:32]}...")
    console.print(f"   device_count = 1")
    console.print(f"   [dim](模拟模式，未实际调用 submit_anchor)[/dim]\n")

    return gops, merkle_tree, htree, segment_root


# ---------------------------------------------------------------------------
# 场景 1: INTACT
# ---------------------------------------------------------------------------

def run_intact_scenario(
    gops: list[GOPData],
    merkle_tree: MerkleTree,
    verifier: TriStateVerifier,
):
    console.print(Panel(
        "[bold green]场景 1: INTACT — 原始视频完整性验证[/bold green]\n"
        "直接验证存证阶段的原始视频，期望所有 GOP 均为 INTACT",
        style="green",
    ))

    tbl = Table(title="INTACT 验证结果", box=box.ROUNDED)
    tbl.add_column("GOP#", justify="right", style="bold")
    tbl.add_column("SHA-256 匹配", justify="center")
    tbl.add_column("pHash 距离", justify="center")
    tbl.add_column("Merkle 证明", justify="center")
    tbl.add_column("判定", justify="center")

    all_pass = True
    passed = 0
    for i, g in enumerate(gops):
        result = verifier.verify(g.sha256_hash, g.phash, g.sha256_hash, g.phash)
        leaf = compute_leaf_hash(g.sha256_hash, g.phash, g.semantic_hash)
        proof = merkle_tree.get_proof(i)
        proof_ok = MerkleTree.verify_proof(leaf, proof, merkle_tree.root)

        if result != "INTACT" or not proof_ok:
            all_pass = False
        else:
            passed += 1

        tbl.add_row(
            str(g.gop_id),
            "[green]YES[/green]",
            "[green]0[/green]",
            "[green]PASS[/green]" if proof_ok else "[red]FAIL[/red]",
            f"[bold green]{result}[/bold green]",
        )

    console.print(tbl)
    if all_pass:
        console.print("[bold green]>>> 场景 1 通过: 所有 GOP 均为 INTACT <<<[/bold green]\n")
    else:
        console.print("[bold red]>>> 场景 1 异常 <<<[/bold red]\n")

    return ScenarioResult(name="INTACT", total=len(gops), expected_count=passed)


# ---------------------------------------------------------------------------
# 场景 2: RE_ENCODED
# ---------------------------------------------------------------------------

def run_re_encoded_scenario(
    video_path: str,
    original_gops: list[GOPData],
    verifier: TriStateVerifier,
    tmp_dir: str,
):
    console.print(Panel(
        "[bold yellow]场景 2: RE_ENCODED — 转码检测[/bold yellow]\n"
        "用 FFmpeg 将原始视频转码 (改码率 500k)，验证转码后的视频",
        style="yellow",
    ))

    if not check_ffmpeg():
        console.print("[red]未找到 ffmpeg，跳过场景 2[/red]\n")
        return ScenarioResult(name="RE_ENCODED", total=0, expected_count=0)

    re_encoded_path = Path(tmp_dir) / "re_encoded.mp4"

    # 转码
    console.print("[yellow]① FFmpeg 转码中 ...[/yellow]")
    console.print(f"   命令: ffmpeg -i input.mp4 -b:v 500k -c:v libx264 -g 30 -keyint_min 30 -sc_threshold 0 -forced-idr 1 re_encoded.mp4")
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", video_path,
            "-b:v", "500k", "-c:v", "libx264",
            "-g", "30", "-keyint_min", "30",
            "-sc_threshold", "0", "-forced-idr", "1",
            "-pix_fmt", "yuv420p",
            str(re_encoded_path),
        ],
        check=True,
        capture_output=True,
    )
    console.print(f"   转码完成: {re_encoded_path}\n")

    # 切分转码后的视频
    console.print("[yellow]② 切分转码后视频 ...[/yellow]")
    re_gops = split_gops(str(re_encoded_path))
    console.print(f"   转码后 GOP 数量: {len(re_gops)}  (原始: {len(original_gops)})")

    if len(re_gops) != len(original_gops):
        console.print(
            f"[dim]   注意: GOP 数量不一致 (原始 {len(original_gops)} vs 转码 {len(re_gops)})[/dim]"
        )

    # 时间戳最近邻匹配
    console.print("[yellow]   按时间戳最近邻匹配 GOP 对 ...[/yellow]\n")
    pairs = match_gops_by_time(original_gops, re_gops)

    # 逐 GOP 验证
    console.print("[yellow]③ 逐 GOP 三态验证 ...[/yellow]")
    tbl = Table(title="RE_ENCODED 验证结果", box=box.ROUNDED)
    tbl.add_column("GOP#", justify="right", style="bold")
    tbl.add_column("原始 SHA-256", style="dim")
    tbl.add_column("转码 SHA-256", style="dim")
    tbl.add_column("时间偏移", justify="center")
    tbl.add_column("pHash 距离", justify="center")
    tbl.add_column("判定", justify="center")

    re_encoded_count = 0
    for og, rg in pairs:
        result = verifier.verify(og.sha256_hash, og.phash, rg.sha256_hash, rg.phash)

        dist = "N/A"
        if og.phash and rg.phash:
            dist = str(hamming_distance(og.phash, rg.phash))

        time_offset = abs(og.start_time - rg.start_time)
        offset_str = f"{time_offset:.3f}s"

        color = "yellow" if result == "RE_ENCODED" else ("green" if result == "INTACT" else "red")
        if result == "RE_ENCODED":
            re_encoded_count += 1

        tbl.add_row(
            str(og.gop_id),
            og.sha256_hash[:12] + "...",
            rg.sha256_hash[:12] + "...",
            f"[dim]{offset_str}[/dim]",
            f"[{color}]{dist}[/{color}]",
            f"[bold {color}]{result}[/bold {color}]",
        )

    console.print(tbl)
    n = len(pairs)
    console.print(
        f"[bold yellow]>>> 场景 2 完成: {re_encoded_count}/{n} 个 GOP 判定为 RE_ENCODED <<<[/bold yellow]\n"
    )

    return ScenarioResult(name="RE_ENCODED", total=n, expected_count=re_encoded_count)


# ---------------------------------------------------------------------------
# 场景 3: TAMPERED + 精确定位
# ---------------------------------------------------------------------------

def run_tampered_scenario(
    original_gops: list[GOPData],
    htree: HierarchicalMerkleTree,
    verifier: TriStateVerifier,
    tamper_gop_idx: int,
):
    console.print(Panel(
        "[bold red]场景 3: TAMPERED — 篡改检测与精确定位[/bold red]\n"
        f"篡改 GOP #{tamper_gop_idx}（翻转字节 + 替换关键帧为噪声），然后验证并定位",
        style="red",
    ))

    if tamper_gop_idx >= len(original_gops):
        console.print(
            f"[red]tamper_gop_idx={tamper_gop_idx} 超出范围 (共 {len(original_gops)} 个 GOP)，"
            f"自动调整为 GOP #0[/red]"
        )
        tamper_gop_idx = 0

    # 深拷贝并篡改
    console.print(f"[red]① 篡改 GOP #{tamper_gop_idx} ...[/red]")
    tampered_gops = copy.deepcopy(original_gops)
    target = tampered_gops[tamper_gop_idx]

    # 翻转 raw_bytes 中间 1024 字节
    corrupted = bytearray(target.raw_bytes)
    mid = len(corrupted) // 2
    flip_len = min(1024, len(corrupted) - mid)
    for j in range(mid, mid + flip_len):
        corrupted[j] = corrupted[j] ^ 0xFF
    target.raw_bytes = bytes(corrupted)
    target.sha256_hash = hashlib.sha256(target.raw_bytes).hexdigest()

    # 替换关键帧为随机噪声
    target.keyframe_frame = np.random.randint(
        0, 256, target.keyframe_frame.shape, dtype=np.uint8
    )
    target.phash = compute_phash(target.keyframe_frame)
    target.semantic_hash = "0" * 64  # 显式占位符，与 compute_leaf_hash 的 None 处理一致

    console.print(f"   已翻转 {flip_len} 字节 + 替换关键帧为随机噪声")
    console.print(f"   新 SHA-256: {target.sha256_hash[:16]}...")
    console.print(f"   新 pHash:   {target.phash}\n")

    # 逐 GOP 验证
    console.print("[red]② 逐 GOP 三态验证 ...[/red]")
    tbl = Table(title="TAMPERED 验证结果", box=box.ROUNDED)
    tbl.add_column("GOP#", justify="right", style="bold")
    tbl.add_column("SHA-256 匹配", justify="center")
    tbl.add_column("pHash 距离", justify="center")
    tbl.add_column("判定", justify="center")

    for i in range(len(original_gops)):
        og = original_gops[i]
        tg = tampered_gops[i]
        result = verifier.verify(og.sha256_hash, og.phash, tg.sha256_hash, tg.phash)

        sha_match = og.sha256_hash == tg.sha256_hash
        dist = "N/A"
        if og.phash and tg.phash:
            dist = str(hamming_distance(og.phash, tg.phash))

        is_tampered_row = (i == tamper_gop_idx)
        row_style = "on red" if is_tampered_row else ""
        color = "red" if result == "TAMPERED" else "green"

        tbl.add_row(
            str(og.gop_id),
            "[green]YES[/green]" if sha_match else "[red]NO[/red]",
            f"[{color}]{dist}[/{color}]",
            f"[bold {color}]{result}[/bold {color}]",
            style=row_style,
        )

    console.print(tbl)

    # 精确定位
    console.print("\n[red]③ Merkle 树篡改定位 (locate_tampered_gops) ...[/red]")
    new_leaf_hashes = [
        compute_leaf_hash(g.sha256_hash, g.phash, g.semantic_hash)
        for g in tampered_gops
    ]
    tampered_indices = htree.locate_tampered_gops(new_leaf_hashes)

    if tampered_indices:
        for idx in tampered_indices:
            g = original_gops[idx]
            loc_text = (
                f"篡改发生在 GOP #{idx}，"
                f"时间范围 {format_time(g.start_time)} - {format_time(g.end_time)}"
            )
            console.print(Panel(
                f"[bold red]{loc_text}[/bold red]",
                title="篡改定位结果",
                style="red",
            ))
        console.print(
            f"[bold red]>>> 场景 3 完成: 检测到 {len(tampered_indices)} 个被篡改的 GOP <<<[/bold red]\n"
        )
    else:
        console.print("[yellow]未检测到篡改 GOP（异常）[/yellow]\n")

    return ScenarioResult(
        name="TAMPERED",
        total=len(original_gops),
        expected_count=len(tampered_indices) if tampered_indices else 0,
        tampered_indices=tampered_indices or [],
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="CCTV 视频证据完整性验证 — 端到端篡改检测演示"
    )
    parser.add_argument("--video", type=str, default=None, help="输入视频路径（不指定则自动生成测试视频）")
    parser.add_argument("--skip-ipfs", action="store_true", help="跳过 IPFS 存储步骤")
    parser.add_argument("--tamper-gop", type=int, default=2, help="场景 3 中要篡改的 GOP 索引 (默认: 2)")
    parser.add_argument(
        "--hamming-threshold", type=int, default=SETTINGS.phash_hamming_threshold,
        help=f"pHash Hamming 距离阈值 (默认: {SETTINGS.phash_hamming_threshold})",
    )
    args = parser.parse_args()

    # 标题
    console.print()
    console.print(Panel(
        "[bold]CCTV 视频证据完整性验证系统[/bold]\n"
        "端到端篡改检测演示  |  三态验证: INTACT / RE_ENCODED / TAMPERED",
        style="bold blue",
        padding=(1, 4),
    ))
    console.print()

    verifier = TriStateVerifier(hamming_threshold=args.hamming_threshold)
    console.print(f"[dim]pHash Hamming 阈值: {args.hamming_threshold} bits[/dim]\n")

    t_start = time.time()

    with tempfile.TemporaryDirectory(prefix="tamper_demo_") as tmp_dir:
        # 准备视频
        video_path = ensure_test_video(args.video, tmp_dir)

        # 存证阶段
        gops, merkle_tree, htree, segment_root = register_video(
            video_path, skip_ipfs=args.skip_ipfs,
        )

        # 场景 1: INTACT
        r1 = run_intact_scenario(gops, merkle_tree, verifier)

        # 场景 2: RE_ENCODED
        r2 = run_re_encoded_scenario(video_path, gops, verifier, tmp_dir)

        # 场景 3: TAMPERED
        r3 = run_tampered_scenario(gops, htree, verifier, args.tamper_gop)

    total_elapsed = time.time() - t_start

    # 一屏汇总 Panel
    tamper_loc = ", ".join(f"#{i}" for i in (r3.tampered_indices or []))
    summary_line = (
        f"✅ INTACT ({r1.expected_count}/{r1.total})  |  "
        f"⚠️  RE_ENCODED ({r2.expected_count}/{r2.total})  |  "
        f"❌ TAMPERED → GOP {tamper_loc} 定位成功"
        if r3.expected_count > 0
        else f"✅ INTACT ({r1.expected_count}/{r1.total})  |  "
             f"⚠️  RE_ENCODED ({r2.expected_count}/{r2.total})  |  "
             f"❌ TAMPERED → 未检测到篡改"
    )
    console.print(Panel(summary_line, title="验证结果一览", style="bold blue"))
    console.print()

    # 总结
    summary = Table(title="演示总结", box=box.DOUBLE, show_lines=True)
    summary.add_column("场景", style="bold")
    summary.add_column("描述")
    summary.add_column("验证逻辑")
    summary.add_row(
        "[green]INTACT[/green]",
        "原始视频直接验证",
        "SHA-256 匹配 → INTACT",
    )
    summary.add_row(
        "[yellow]RE_ENCODED[/yellow]",
        "FFmpeg 转码 (改码率)",
        f"SHA-256 不匹配 + pHash 距离 ≤ {args.hamming_threshold} → RE_ENCODED",
    )
    summary.add_row(
        "[red]TAMPERED[/red]",
        "字节翻转 + 关键帧替换",
        f"SHA-256 不匹配 + pHash 距离 > {args.hamming_threshold} → TAMPERED\n"
        "locate_tampered_gops() 精确定位",
    )
    console.print(summary)
    console.print(f"\n[bold blue]演示完成  |  总耗时: {total_elapsed:.2f}s[/bold blue]\n")


if __name__ == "__main__":
    main()
