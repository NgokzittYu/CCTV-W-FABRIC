"""
SecureLens Demo — 独立演示前端。

单命令启动：python demo/app.py
不依赖 Fabric / MinIO，使用 YOLO nano 轻量模型。
"""

import base64
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path

import av
import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

# 启用 VIF 融合模式（默认 off）
os.environ.setdefault("VIF_MODE", "fusion")

# 确保项目根目录在 sys.path 中
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.perceptual_hash import compute_phash, hamming_distance
from services.merkle_utils import compute_leaf_hash, MerkleTree
from services.tri_state_verifier import TriStateVerifier
from services.mab_anchor import MABAnchorManager, ARM_INTERVALS
from services.gop_splitter import split_gops
from benchmarks.datasets import apply_tamper

# YOLO 延迟加载
_yolo_model = None

def _get_yolo():
    global _yolo_model
    if _yolo_model is None:
        from ultralytics import YOLO
        _yolo_model = YOLO("yolo11n.pt")
        print("✅ YOLO nano 模型已加载")
    return _yolo_model

app = Flask(__name__)

SAMPLES_DIR = Path(__file__).parent / "static" / "samples"
UPLOAD_DIR = Path(tempfile.gettempdir()) / "securelens_demo"
UPLOAD_DIR.mkdir(exist_ok=True)


# ─── Pages ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/analyze")
def analyze():
    return render_template("analyze.html")


@app.route("/detect")
def detect():
    return render_template("detect.html")


@app.route("/benchmark")
def benchmark():
    return render_template("benchmark.html")


# ─── API: List samples ───────────────────────────────────────────────

@app.route("/api/samples")
def list_samples():
    samples = []
    if SAMPLES_DIR.exists():
        for f in sorted(SAMPLES_DIR.iterdir()):
            if f.suffix in (".mp4", ".avi", ".mov", ".mkv"):
                samples.append({"name": f.stem, "filename": f.name})
    return jsonify({"samples": samples})


# ─── API: Analyze video (SSE) ────────────────────────────────────────

@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """分析视频：GOP 切分 + 哈希 + VIF + Merkle。SSE 推送进度。"""

    # 获取视频文件
    video_path = _get_video_from_request()
    if not video_path:
        return jsonify({"error": "No video provided"}), 400

    def generate():
        try:
            # Step 1: GOP 切分 + 哈希 + VIF（使用原项目 split_gops）
            yield _sse("progress", {"step": 1, "label": "GOP 切分 + 指纹计算中…", "status": "running"})
            gop_data_list = split_gops(str(video_path))
            vif_available = any(g.vif is not None for g in gop_data_list)
            yield _sse("progress", {"step": 1, "label": "GOP 切分 + 指纹", "status": "done",
                        "detail": f"{len(gop_data_list)} 个 GOP · SHA-256 · pHash" + (" · VIF" if vif_available else "")})

            # Step 2: YOLO 目标检测
            yield _sse("progress", {"step": 2, "label": "YOLO 检测中…", "status": "running"})
            model = _get_yolo()
            gop_results = []
            total_detections = 0
            for i, gop in enumerate(gop_data_list):
                keyframe_bgr = gop.keyframe_frame  # split_gops 返回 BGR
                results = model(keyframe_bgr, verbose=False)
                det = results[0]
                boxes = det.boxes
                det_count = len(boxes)
                total_detections += det_count

                # 提取检测结果
                detections = []
                obj_counts = {}
                for box in boxes:
                    cls_id = int(box.cls[0])
                    cls_name = det.names[cls_id]
                    conf = float(box.conf[0])
                    detections.append({"class": cls_name, "confidence": round(conf, 3)})
                    obj_counts[cls_name] = obj_counts.get(cls_name, 0) + 1

                # 绘制检测框到缩略图
                ann_frame = det.plot()  # BGR with boxes
                thumb = _frame_to_base64_bgr(ann_frame, max_width=200)

                gop_results.append({
                    "gop_id": gop.gop_id,
                    "frame_count": gop.frame_count,
                    "sha256": gop.sha256_hash,
                    "phash": gop.phash,
                    "vif": gop.vif,
                    "byte_size": gop.byte_size,
                    "time_range": f"{gop.start_time:.1f}s - {gop.end_time:.1f}s",
                    "thumbnail": thumb,
                    "detections": detections,
                    "obj_counts": obj_counts,
                    "det_count": det_count,
                })
            yield _sse("progress", {"step": 2, "label": "YOLO 检测", "status": "done", "detail": f"{total_detections} 个目标"})

            # Step 3: EIS 评分 + MAB 决策
            yield _sse("progress", {"step": 3, "label": "EIS + MAB 决策中…", "status": "running"})
            mab = MABAnchorManager(mode="mab_ucb", auto_load=False)
            for i, r in enumerate(gop_results):
                # EIS：使用原项目 SemanticFingerprint 数据
                gop = gop_data_list[i]
                if gop.semantic_fingerprint:
                    det_count = gop.semantic_fingerprint.total_count
                    person_count = gop.semantic_fingerprint.objects.get("person", 0)
                else:
                    det_count = r["det_count"]
                    person_count = r["obj_counts"].get("person", 0)
                if det_count == 0:
                    eis_score = 0.1
                elif det_count <= 3:
                    eis_score = 0.3
                elif det_count <= 8:
                    eis_score = 0.6
                else:
                    eis_score = 0.9
                if person_count >= 3:
                    eis_score = min(1.0, eis_score + 0.1)

                should_anchor = mab.should_anchor(i)
                if should_anchor:
                    # 成本与锚定频率成正比（interval 越小 → 频率越高 → 成本越高）
                    arm_interval = ARM_INTERVALS[mab.current_arm]
                    anchor_cost = 1.0 / arm_interval  # arm0(1)=1.0, arm1(2)=0.5, arm2(5)=0.2, arm3(10)=0.1
                    # 延迟与场景重要性相关（EIS 高 → 重要场景 → 低延迟容忍 → 惩罚更重）
                    anchor_latency = eis_score * 2.0  # [0, 2.0]s
                    mab.report_result(success=True, cost=anchor_cost, latency=anchor_latency)

                r["eis_score"] = round(eis_score, 2)
                r["should_anchor"] = should_anchor
                r["mab_arm"] = mab.current_arm
                r["mab_interval"] = mab.current_interval

            mab_stats = mab.get_stats()
            yield _sse("progress", {"step": 3, "label": "EIS + MAB", "status": "done",
                        "detail": f"arm={mab_stats['current_arm']} interval={mab_stats['current_interval']}"})

            # Step 4: Merkle 树构建
            yield _sse("progress", {"step": 4, "label": "Merkle 构建中…", "status": "running"})
            leaf_hashes = []
            for r in gop_results:
                leaf = compute_leaf_hash(
                    r["sha256"],
                    phash=r["phash"],
                    vif=r.get("vif"),
                )
                r["leaf_hash"] = leaf
                leaf_hashes.append(leaf)

            tree = MerkleTree(leaf_hashes)
            merkle_root = tree.root
            
            # 构造用于前端 ECharts 的树形数据
            def _build_tree(level_idx, node_idx):
                node_hash = tree._levels[level_idx][node_idx]
                short_hash = node_hash[:8] + "…"
                
                if level_idx == 0:
                    # 叶子节点
                    is_padded = node_idx >= len(gop_results)
                    if is_padded:
                        return {"name": "Pad", "value": node_hash, "symbolSize": 5, "itemStyle": {"color": "#E5E7EB"}}
                    gop = gop_results[node_idx]
                    return {
                        "name": f"GOP {gop['gop_id']}\n{short_hash}",
                        "value": node_hash,
                        "symbol": f"image://{gop['thumbnail']}",
                        "symbolSize": [42, 30],  # 宽, 高
                    }
                else:
                    # 中间节点
                    children = []
                    left_idx = node_idx * 2
                    right_idx = left_idx + 1
                    
                    if left_idx < len(tree._levels[level_idx - 1]):
                        children.append(_build_tree(level_idx - 1, left_idx))
                    if right_idx < len(tree._levels[level_idx - 1]):
                        children.append(_build_tree(level_idx - 1, right_idx))
                        
                    name = "Root" if level_idx == len(tree._levels) - 1 else "Node"
                    return {
                        "name": f"{name}\n{short_hash}",
                        "value": node_hash,
                        "children": children,
                        "symbolSize": 12,
                        "itemStyle": {"color": "#8B5CF6" if name == "Root" else "#3B82F6"}
                    }
                    
            tree_data = _build_tree(len(tree._levels) - 1, 0)

            merkle_data = {
                "root": merkle_root,
                "leaf_count": len(leaf_hashes),
                "leaves": leaf_hashes,
                "tree_data": tree_data,
            }
            yield _sse("progress", {"step": 4, "label": "Merkle 构建", "status": "done", "detail": f"root={merkle_root[:16]}…"})

            # 最终结果
            yield _sse("result", {
                "gops": gop_results,
                "merkle": merkle_data,
                "vif_available": vif_available,
                "mab_stats": mab_stats,
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            yield _sse("error", {"message": str(e)})

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ─── API: Tamper generation ──────────────────────────────────────────

# 全局存储：篡改结果（用于 detect 对比）
_tamper_store: dict = {}


def _reencode_gop_tampered(
    gop,
    tamper_fn,
    vif_config=None,
):
    """解码 GOP 全帧 → 逐帧篡改 → PyAV 重编码 → 提取 MV + 计算 VIF。

    Args:
        gop: GOPData 对象（含 keyframe_frame, raw_bytes 等）
        tamper_fn: Callable(frame) -> tampered_frame，像素级篡改函数
        vif_config: VIFConfig（为 None 则自动读取）

    Returns:
        dict: {sha256, phash, vif, keyframe, motion_vectors}
    """
    import av as _av
    import io as _io
    from services.vif import VIFConfig, compute_vif

    if vif_config is None:
        vif_config = VIFConfig()

    # ── 1. 解码原始 GOP 所有帧 ──
    orig_frames = [gop.keyframe_frame]
    try:
        container = _av.open(_io.BytesIO(gop.raw_bytes))
        vs = container.streams.video[0]
        count = 0
        for pkt in container.demux(vs):
            if pkt.size == 0:
                continue
            try:
                for frm in vs.codec_context.decode(pkt):
                    count += 1
                    if count > 1:  # 跳过 keyframe（已有）
                        orig_frames.append(frm.to_ndarray(format="bgr24"))
            except Exception:
                pass
        container.close()
    except Exception:
        pass

    # ── 2. 逐帧篡改 ──
    tampered_frames = [tamper_fn(f) for f in orig_frames]

    # ── 3. PyAV 重编码为合法 H.264 ──
    h, w = tampered_frames[0].shape[:2]
    buf = _io.BytesIO()
    try:
        out = _av.open(buf, mode='w', format='mp4')
        vstream = out.add_stream('libx264', rate=30)
        vstream.width = w
        vstream.height = h
        vstream.pix_fmt = 'yuv420p'
        vstream.options = {'preset': 'ultrafast', 'crf': '23'}

        for tf in tampered_frames:
            av_frame = _av.VideoFrame.from_ndarray(tf, format='bgr24')
            for packet in vstream.encode(av_frame):
                out.mux(packet)
        for packet in vstream.encode():
            out.mux(packet)
        out.close()
    except Exception as e:
        print(f"[REENCODE] 编码失败: {e}")
        # 回退：直接用篡改后 keyframe 的 SHA
        t_sha = hashlib.sha256(tampered_frames[0].tobytes()).hexdigest()
        return {
            "sha256": t_sha,
            "phash": compute_phash(tampered_frames[0]),
            "vif": compute_vif(tampered_frames, vif_config) if vif_config.mode != "off" else None,
            "keyframe": tampered_frames[0],
        }

    raw_bytes = buf.getvalue()
    t_sha = hashlib.sha256(raw_bytes).hexdigest()

    # ── 4. 重新打开以解码完整帧 ──
    decoded_frames = []
    try:
        container2 = _av.open(_io.BytesIO(raw_bytes))
        vs2 = container2.streams.video[0]
        for pkt in container2.demux(vs2):
            if pkt.size == 0:
                continue
            try:
                for frm in vs2.codec_context.decode(pkt):
                    decoded_frames.append(frm.to_ndarray(format="bgr24"))
            except Exception:
                pass
        container2.close()
    except Exception as e:
        print(f"[REENCODE] 重新解码失败: {e}")

    # ── 5. 计算 VIF（带 MV 标记）──
    # 关键：帧采样必须与 _build_gop 一致（keyframe + VIF_SAMPLE_FRAMES 采样帧）
    # 否则 Farneback 特征维度不同 → D_tem ≈ 0.50
    t_vif = None
    if vif_config.mode != "off":
        all_frames = decoded_frames if decoded_frames else tampered_frames
        vif_sample_n = int(os.environ.get("VIF_SAMPLE_FRAMES", "1"))
        if len(all_frames) > 1 + vif_sample_n:
            total_extra = len(all_frames) - 1
            if vif_sample_n == 1:
                sampled_indices = [1 + total_extra // 2]
            else:
                step = total_extra / vif_sample_n
                sampled_indices = [1 + int(i * step + step / 2) for i in range(vif_sample_n)]
            vif_frames = [all_frames[0]] + [all_frames[idx] for idx in sampled_indices]
        else:
            vif_frames = all_frames
        try:
            t_vif = compute_vif(vif_frames, vif_config)
        except Exception:
            pass

    keyframe = decoded_frames[0] if decoded_frames else tampered_frames[0]

    return {
        "sha256": t_sha,
        "phash": compute_phash(keyframe),
        "vif": t_vif,
        "keyframe": keyframe,
    }

@app.route("/api/tamper", methods=["POST"])
def api_tamper():
    """生成篡改视频帧，保存到内存供检测对比。"""
    video_path = _get_video_from_request()
    if not video_path:
        return jsonify({"error": "No video provided"}), 400

    tamper_type = request.form.get("tamper_type", "frame_replace")
    intensity = float(request.form.get("intensity", "0.5"))

    gop_data_list = split_gops(str(video_path))
    if not gop_data_list:
        return jsonify({"error": "No GOPs found"}), 400

    if tamper_type == "mid_frame":
        # ─── 帧间篡改：修改 P/B 帧字节，保留 I 帧 ───
        import av as _av

        orig_gop_info = []   # 每个 GOP: {sha256, phash, vif, keyframe}
        tampered_gop_info = []
        tampered_frames_info = []

        for i, gop in enumerate(gop_data_list):
            orig_gop_info.append({
                "sha256": gop.sha256_hash,
                "phash": gop.phash,
                "vif": gop.vif,
                "keyframe": gop.keyframe_frame,
            })

            if i % 2 == 0:  # 每隔一个 GOP 篡改
                raw = bytearray(gop.raw_bytes)
                # 找到 raw bytes 中 P/B 帧区域（跳过前 20% 假定为 I 帧区域）
                i_end = max(64, len(raw) // 5)
                pb_region = raw[i_end:]
                if len(pb_region) > 0:
                    rng = np.random.RandomState(seed=i + 1000)
                    n_corrupt = max(1, int(len(pb_region) * intensity * 0.3))
                    positions = rng.randint(0, len(pb_region), size=n_corrupt)
                    for pos in positions:
                        pb_region[pos] = rng.randint(0, 256)
                    raw[i_end:] = pb_region

                tampered_sha256 = hashlib.sha256(bytes(raw)).hexdigest()

                # 重新计算 VIF（用篡改后的字节解码帧 + 收集 MV）
                tampered_vif = None
                try:
                    from services.vif import VIFConfig, compute_vif
                    vif_config = VIFConfig()
                    if vif_config.mode != "off":
                        import io as _io
                        tampered_frames_list = [gop.keyframe_frame]  # I帧不变
                        try:
                            container = _av.open(_io.BytesIO(bytes(raw)))
                            vs = container.streams.video[0]
                            decoded_count = 0
                            for pkt in container.demux(vs):
                                if pkt.size == 0:
                                    continue
                                try:
                                    for frm in vs.codec_context.decode(pkt):
                                        decoded_count += 1
                                        if decoded_count > 1 and decoded_count % 5 == 0:
                                            tampered_frames_list.append(frm.to_ndarray(format="bgr24"))
                                except Exception:
                                    pass
                            container.close()
                        except Exception:
                            pass
                        tampered_vif = compute_vif(
                            tampered_frames_list, vif_config,
                        )
                except Exception:
                    pass

                tampered_gop_info.append({
                    "sha256": tampered_sha256,
                    "phash": gop.phash,  # I帧不变 → pHash 不变
                    "vif": tampered_vif,
                    "keyframe": gop.keyframe_frame,
                })
                tampered_frames_info.append({
                    "index": i,
                    "tampered": True,
                    "thumbnail": _frame_to_base64_bgr(gop.keyframe_frame, max_width=200),
                })
            else:
                tampered_gop_info.append(orig_gop_info[-1].copy())
                tampered_frames_info.append({
                    "index": i,
                    "tampered": False,
                    "thumbnail": _frame_to_base64_bgr(gop.keyframe_frame, max_width=200),
                })

        tamper_id = f"tamper_{int(time.time())}"
        _tamper_store[tamper_id] = {
            "tamper_type": "mid_frame",
            "mode": "gop_level",
            "orig_gop_info": orig_gop_info,
            "tampered_gop_info": tampered_gop_info,
        }
    else:
        # ─── 像素级篡改 + MV tag 一致性 ───
        # 对 keyframe 施加篡改，传原始 MV 确保 tag='m' 匹配
        from services.vif import VIFConfig, compute_vif

        vif_config = VIFConfig()
        orig_gop_info = []
        tampered_gop_info = []
        tampered_frames_info = []

        for i, gop in enumerate(gop_data_list):
            kf = gop.keyframe_frame
            orig_gop_info.append({
                "sha256": gop.sha256_hash,
                "phash": gop.phash,
                "vif": gop.vif,
                "keyframe": kf,
            })

            if i % 2 == 0:  # 每隔一个 GOP 篡改
                t_frame = apply_tamper(kf, tamper_type, intensity, seed=i)
                t_sha256 = hashlib.sha256(t_frame.tobytes()).hexdigest()
                t_phash = compute_phash(t_frame)
                t_vif = None
                if vif_config.mode != "off":
                        t_vif = compute_vif(
                            [t_frame], vif_config,
                        )
                    except Exception:
                        pass

                tampered_gop_info.append({
                    "sha256": t_sha256,
                    "phash": t_phash,
                    "vif": t_vif,
                    "keyframe": t_frame,
                })
                tampered_frames_info.append({
                    "index": i,
                    "tampered": True,
                    "thumbnail": _frame_to_base64_bgr(t_frame, max_width=200),
                })
            else:
                tampered_gop_info.append(orig_gop_info[-1].copy())
                tampered_frames_info.append({
                    "index": i,
                    "tampered": False,
                    "thumbnail": _frame_to_base64_bgr(kf, max_width=200),
                })

        tamper_id = f"tamper_{int(time.time())}"
        _tamper_store[tamper_id] = {
            "tamper_type": tamper_type,
            "mode": "gop_level",
            "orig_gop_info": orig_gop_info,
            "tampered_gop_info": tampered_gop_info,
        }

    # 清理旧条目
    while len(_tamper_store) > 5:
        oldest = next(iter(_tamper_store))
        del _tamper_store[oldest]

    return jsonify({
        "frames": tampered_frames_info,
        "tamper_type": tamper_type,
        "tamper_id": tamper_id,
        "total_gops": len(gop_data_list),
        "tampered_count": sum(1 for f in tampered_frames_info if f["tampered"]),
    })


# ─── API: Detect tampering ───────────────────────────────────────────

@app.route("/api/detect", methods=["POST"])
def api_detect():
    """检测篡改：对比原始 vs 可疑帧。"""

    tamper_id = request.form.get("tamper_id")

    if tamper_id and tamper_id in _tamper_store:
        store = _tamper_store[tamper_id]

        if store.get("mode") == "gop_level":
            # ─── 统一的 GOP 级别对比（VIF v2 加权评分） ───
            orig_list = store["orig_gop_info"]
            tampered_list = store["tampered_gop_info"]
            verifier = TriStateVerifier()
            comparisons = []

            for i in range(min(len(orig_list), len(tampered_list))):
                o = orig_list[i]
                t = tampered_list[i]

                state, risk, details = verifier.verify(
                    o["sha256"], t["sha256"],
                    o.get("vif"), t.get("vif"),
                )

                comparisons.append({
                    "frame_index": i,
                    "state": state,
                    "state_desc": details.get("state_desc", state),
                    "risk_score": round(risk, 4),
                    "d_vis": details.get("d_vis"),
                    "sha_match": o["sha256"] == t["sha256"],
                    "orig_thumb": _frame_to_base64_bgr(o["keyframe"], max_width=160),
                    "suspect_thumb": _frame_to_base64_bgr(t["keyframe"], max_width=160),
                })
        else:
            # ─── 兼容旧格式的关键帧对比（VIF v2） ───
            orig_frames = store["orig_keyframes"]
            suspect_frames = store["tampered_keyframes"]
            comparisons = []

            for i in range(min(len(orig_frames), len(suspect_frames))):
                orig_sha = hashlib.sha256(orig_frames[i].tobytes()).hexdigest()
                susp_sha = hashlib.sha256(suspect_frames[i].tobytes()).hexdigest()

                comparisons.append({
                    "frame_index": i,
                    "state": "INTACT" if orig_sha == susp_sha else "TAMPERED",
                    "risk_score": 0.0 if orig_sha == susp_sha else 1.0,
                    "sha_match": orig_sha == susp_sha,
                    "orig_thumb": _frame_to_base64_bgr(orig_frames[i], max_width=160),
                    "suspect_thumb": _frame_to_base64_bgr(suspect_frames[i], max_width=160),
                })
    else:
        # 传统模式：上传两个视频对比
        orig_path = None
        suspect_path = None

        if "original" in request.files:
            f = request.files["original"]
            orig_path = UPLOAD_DIR / f"orig_{int(time.time())}.mp4"
            f.save(str(orig_path))
        elif request.form.get("original_sample"):
            orig_path = SAMPLES_DIR / request.form["original_sample"]

        if "suspect" in request.files:
            f = request.files["suspect"]
            suspect_path = UPLOAD_DIR / f"suspect_{int(time.time())}.mp4"
            f.save(str(suspect_path))

        if not orig_path or not orig_path.exists():
            return jsonify({"error": "Original video required"}), 400

        orig_gops = split_gops(str(orig_path))
        orig_frames = [g.keyframe_frame for g in orig_gops]

        if suspect_path and suspect_path.exists():
            suspect_gops = split_gops(str(suspect_path))
            suspect_frames = [g.keyframe_frame for g in suspect_gops]
        else:
            suspect_frames = orig_frames

        # 使用 VIF v2 对 GOP 级别对比
        verifier = TriStateVerifier()
        comparisons = []

        for i in range(min(len(orig_gops), len(suspect_gops) if suspect_path else len(orig_gops))):
            og = orig_gops[i]
            sg = suspect_gops[i] if suspect_path and suspect_path.exists() else og

            state, risk, details = verifier.verify(
                og.sha256_hash, sg.sha256_hash,
                og.vif, sg.vif,
            )

            comparisons.append({
                "frame_index": i,
                "state": state,
                "state_desc": details.get("state_desc", state),
                "risk_score": round(risk, 4),
                "d_vis": details.get("d_vis"),
                "sha_match": og.sha256_hash == sg.sha256_hash,
                "orig_thumb": _frame_to_base64_bgr(og.keyframe_frame, max_width=160),
                "suspect_thumb": _frame_to_base64_bgr(sg.keyframe_frame, max_width=160),
            })

    # 总体判定
    states = [c["state"] for c in comparisons]
    if all(s == "INTACT" for s in states):
        overall = "INTACT"
    elif any(s == "TAMPERED" for s in states):
        overall = "TAMPERED"
    else:
        overall = "RE_ENCODED"

    return jsonify({
        "overall": overall,
        "frame_count": len(comparisons),
        "comparisons": comparisons,
    })


# ─── API: Benchmark data ─────────────────────────────────────────────

@app.route("/api/benchmark")
def api_benchmark():
    results_path = ROOT / "benchmark_results" / "results.json"
    if results_path.exists():
        return jsonify(json.loads(results_path.read_text()))
    return jsonify({"error": "No benchmark results found"}), 404


# ─── Helpers ──────────────────────────────────────────────────────────

def _get_video_from_request():
    """从请求中获取视频路径。"""
    if "video" in request.files:
        f = request.files["video"]
        path = UPLOAD_DIR / f"upload_{int(time.time())}.mp4"
        f.save(str(path))
        return path
    sample = request.form.get("sample")
    if sample:
        path = SAMPLES_DIR / sample
        if path.exists():
            return path
    return None


def _frame_to_base64_bgr(frame_bgr, max_width=200):
    """BGR 帧转 base64 缩略图。"""
    h, w = frame_bgr.shape[:2]
    if w > max_width:
        scale = max_width / w
        frame_bgr = cv2.resize(frame_bgr, (max_width, int(h * scale)))
    _, buf = cv2.imencode(".jpg", frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode()





def _sse(event, data):
    """格式化 SSE 消息。"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


if __name__ == "__main__":
    print("🔐 SecureLens Demo — http://localhost:5001")
    app.run(host="0.0.0.0", port=5001, debug=True)
