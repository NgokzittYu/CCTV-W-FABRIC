"""GOP-level video stream splitter using PyAV.

Splits a live CCTV stream (or local MP4 file) into GOP segments by detecting
keyframe boundaries at the packet level. Each GOP's raw encoded bytes are
SHA-256 hashed for content-addressable evidence integrity.

For intra-only codecs (MJPEG) where every frame is a keyframe, packets are
grouped into logical GOPs of a configurable size (default 25 frames).
"""
import argparse
import base64
import hashlib
import os
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union

import av
import numpy as np

from services.gop_timing import normalize_gop_bounds
from services.perceptual_hash import compute_phash
from services.semantic_fingerprint import SemanticExtractor, SemanticFingerprint

# Codecs where every frame is an I-frame (no P/B frames)
_INTRA_ONLY_CODECS = {"mjpeg", "rawvideo", "png", "bmp", "tiff"}

# Default number of frames per logical GOP for intra-only codecs
DEFAULT_MJPEG_GOP_SIZE = 25


@dataclass
class GOPData:
    """A single GOP (Group of Pictures) segment."""

    gop_id: int
    raw_bytes: bytes                # all packet bytes concatenated
    sha256_hash: str                # hex digest of raw_bytes
    start_time: float               # seconds (PTS-based)
    end_time: float                 # seconds
    frame_count: int
    byte_size: int
    keyframe_frame: np.ndarray      # I-frame decoded as BGR numpy array
    phash: Optional[str] = None     # perceptual hash of keyframe (hex string)
    semantic_hash: Optional[str] = None  # semantic fingerprint hash
    semantic_fingerprint: Optional[SemanticFingerprint] = None  # full semantic data
    vif: Optional[str] = None        # multi-modal fusion fingerprint (VIF)
    codec_name: Optional[str] = None
    codec_extradata_b64: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    pix_fmt: Optional[str] = None
    time_base_num: Optional[int] = None
    time_base_den: Optional[int] = None
    frame_rate_num: Optional[int] = None
    frame_rate_den: Optional[int] = None
    packet_sizes: Optional[List[int]] = None
    packet_pts: Optional[List[Optional[int]]] = None
    packet_dts: Optional[List[Optional[int]]] = None
    packet_keyframes: Optional[List[bool]] = None


@dataclass
class PendingGOP:
    """A lightweight GOP payload waiting for expensive fingerprint construction."""

    session_seq: int
    gop_id: int
    raw_bytes: bytes
    start_ts: float
    end_ts: float
    frame_count: int
    keyframe_frame: np.ndarray
    stream_metadata: Dict[str, Optional[object]]
    packet_sizes: List[int]
    packet_pts: List[Optional[int]]
    packet_dts: List[Optional[int]]
    packet_keyframes: List[bool]
    queued_at: float


_PREWARM_LOCK = threading.Lock()
_PREWARM_DONE = False


def prewarm_gop_processors():
    """Warm up expensive fingerprinting components before live ingest begins."""
    global _PREWARM_DONE
    if _PREWARM_DONE:
        return
    with _PREWARM_LOCK:
        if _PREWARM_DONE:
            return
        try:
            from services.perceptual_hash import _get_deep_hasher

            _get_deep_hasher()._load_model()
        except Exception as e:
            print(f"[GOP_SPLITTER] Warning: perceptual hasher prewarm failed: {e}")
        try:
            extractor = SemanticExtractor.get_instance()
            extractor._load_model()
        except Exception as e:
            print(f"[GOP_SPLITTER] Warning: semantic extractor prewarm failed: {e}")
        try:
            from services.vif import VIFConfig, _PHASH_FEAT_DIM, _VIFLSHProjector

            projector = _VIFLSHProjector.get_instance()
            projector._get_projection_matrix(_PHASH_FEAT_DIM, VIFConfig().output_length)
        except Exception as e:
            print(f"[GOP_SPLITTER] Warning: VIF prewarm failed: {e}")
        _PREWARM_DONE = True


# ---------------------------------------------------------------------------
# Internal: detect whether the codec is intra-only
# ---------------------------------------------------------------------------

def _is_intra_only(stream: av.video.stream.VideoStream) -> bool:
    """Return True if the stream codec produces only keyframes (e.g. MJPEG)."""
    return stream.codec_context.name in _INTRA_ONLY_CODECS


# ---------------------------------------------------------------------------
# Internal: decode a keyframe packet into BGR numpy array
# ---------------------------------------------------------------------------

def _decode_keyframe(packet: av.Packet, stream: av.video.stream.VideoStream) -> np.ndarray:
    """Decode the keyframe packet and return a BGR numpy array.

    Uses the stream's own codec_context which already has SPS/PPS and full
    decoder state, avoiding the empty-decode issue with a fresh CodecContext.
    """
    try:
        frames = stream.codec_context.decode(packet)
        if frames:
            return frames[0].to_ndarray(format="bgr24")
    except av.error.InvalidDataError:
        pass

    # Fallback: return empty array if decode somehow fails
    print("[GOP_SPLITTER] Warning: keyframe decode returned no frames")
    return np.zeros(
        (stream.codec_context.height, stream.codec_context.width, 3),
        dtype=np.uint8,
    )


def _packet_ts(packet: av.Packet, stream: av.video.stream.VideoStream) -> float:
    """Extract timestamp in seconds, with None-safety."""
    if packet.pts is not None:
        return float(packet.pts * stream.time_base)
    return 0.0


def _fraction_parts(value) -> tuple[Optional[int], Optional[int]]:
    """Convert av Rational-like objects to (num, den)."""
    if value is None:
        return None, None
    try:
        return int(value.numerator), int(value.denominator)
    except Exception:
        return None, None


def _extract_stream_metadata(stream: av.video.stream.VideoStream) -> Dict[str, Optional[object]]:
    """Capture the minimum codec metadata needed to remux GOP packets later."""
    codec_ctx = stream.codec_context
    time_base_num, time_base_den = _fraction_parts(stream.time_base)
    frame_rate_num, frame_rate_den = _fraction_parts(stream.average_rate or stream.base_rate)
    pix_fmt = None
    try:
        pix_fmt = codec_ctx.format.name if codec_ctx.format is not None else None
    except Exception:
        pix_fmt = None

    extradata = codec_ctx.extradata or b""
    return {
        "codec_name": codec_ctx.name,
        "codec_extradata_b64": base64.b64encode(extradata).decode("ascii") if extradata else None,
        "width": codec_ctx.width or None,
        "height": codec_ctx.height or None,
        "pix_fmt": pix_fmt,
        "time_base_num": time_base_num,
        "time_base_den": time_base_den,
        "frame_rate_num": frame_rate_num,
        "frame_rate_den": frame_rate_den,
    }


# ---------------------------------------------------------------------------
# Internal: build a GOPData from accumulated state
# ---------------------------------------------------------------------------

def _build_gop(
    gop_id: int,
    buf: bytearray,
    start_ts: float,
    end_ts: float,
    frame_count: int,
    keyframe_frame: np.ndarray,
    stream_metadata: Optional[Dict[str, Optional[object]]] = None,
    packet_sizes: Optional[List[int]] = None,
    packet_pts: Optional[List[Optional[int]]] = None,
    packet_dts: Optional[List[Optional[int]]] = None,
    packet_keyframes: Optional[List[bool]] = None,
    extra_frames: Optional[List[np.ndarray]] = None,
) -> GOPData:
    raw = bytes(buf)
    sha256_hash = hashlib.sha256(raw).hexdigest()
    phash = compute_phash(keyframe_frame)
    metadata = stream_metadata or {}
    norm_start, norm_end, _ = normalize_gop_bounds(
        start_ts,
        end_ts,
        packet_pts=packet_pts,
        time_base_num=metadata.get("time_base_num"),
        time_base_den=metadata.get("time_base_den"),
        frame_rate_num=metadata.get("frame_rate_num"),
        frame_rate_den=metadata.get("frame_rate_den"),
    )

    # Compute semantic fingerprint
    semantic_fp = None
    semantic_hash = None
    try:
        extractor = SemanticExtractor.get_instance()
        semantic_fp = extractor.extract(
            keyframe_frame=keyframe_frame,
            gop_id=gop_id,
            start_time=norm_start
        )
        if semantic_fp:
            semantic_hash = semantic_fp.semantic_hash
    except Exception as e:
        print(f"[GOP_SPLITTER] 警告：语义提取失败 GOP {gop_id}: {e}")

    # Compute VIF (multi-modal fusion fingerprint)
    vif_str = None
    try:
        from services.vif import VIFConfig, compute_vif
        vif_config = VIFConfig()
        if vif_config.mode != "off":
            gop_frames = [keyframe_frame]
            if extra_frames:
                gop_frames.extend(extra_frames)
            vif_str = compute_vif(
                gop_frames, vif_config
            )
    except Exception as e:
        print(f"[GOP_SPLITTER] 警告：VIF 计算失败 GOP {gop_id}: {e}")

    return GOPData(
        gop_id=gop_id,
        raw_bytes=raw,
        sha256_hash=sha256_hash,
        start_time=norm_start,
        end_time=norm_end,
        frame_count=frame_count,
        byte_size=len(raw),
        keyframe_frame=keyframe_frame,
        phash=phash,
        semantic_hash=semantic_hash,
        semantic_fingerprint=semantic_fp,
        vif=vif_str,
        codec_name=metadata.get("codec_name"),
        codec_extradata_b64=metadata.get("codec_extradata_b64"),
        width=metadata.get("width"),
        height=metadata.get("height"),
        pix_fmt=metadata.get("pix_fmt"),
        time_base_num=metadata.get("time_base_num"),
        time_base_den=metadata.get("time_base_den"),
        frame_rate_num=metadata.get("frame_rate_num"),
        frame_rate_den=metadata.get("frame_rate_den"),
        packet_sizes=list(packet_sizes or []),
        packet_pts=list(packet_pts or []),
        packet_dts=list(packet_dts or []),
        packet_keyframes=list(packet_keyframes or []),
    )


# ---------------------------------------------------------------------------
# Offline helper – split a local video into GOPs and return the full list
# ---------------------------------------------------------------------------

def split_gops(video_path: str, mjpeg_gop_size: int = DEFAULT_MJPEG_GOP_SIZE) -> List[GOPData]:
    """Split a local video file into GOPs and return all segments.

    Args:
        video_path: Path to a local video file.
        mjpeg_gop_size: For intra-only codecs (MJPEG), how many frames
            per logical GOP.  Ignored for inter-frame codecs (H.264 etc.).

    This is the offline / batch variant used for debugging and testing.
    """
    container = av.open(video_path)
    video_stream = container.streams.video[0]
    intra_only = _is_intra_only(video_stream)
    stream_metadata = _extract_stream_metadata(video_stream)

    if intra_only:
        print(f"[GOP_SPLITTER] Intra-only codec ({video_stream.codec_context.name}), "
              f"grouping every {mjpeg_gop_size} frames as one logical GOP")

    # VIF 多帧采样设置
    vif_mode = os.environ.get("VIF_MODE", "off").strip().lower()
    vif_sample_n = int(os.environ.get("VIF_SAMPLE_FRAMES", "1"))
    need_extra = (vif_mode != "off" and vif_sample_n > 0)

    gops: List[GOPData] = []
    gop_id = 0

    buf = bytearray()
    frame_count = 0
    start_ts = 0.0
    end_ts = 0.0
    pending_keyframe: Optional[np.ndarray] = None
    # 缓存当前 GOP 的非关键帧 packets，用于解码采样
    gop_packets: List[av.Packet] = []
    packet_sizes: List[int] = []
    packet_pts: List[Optional[int]] = []
    packet_dts: List[Optional[int]] = []
    packet_keyframes: List[bool] = []

    def _sample_extra_frames(packets: List[av.Packet], stream) -> List[np.ndarray]:
        """从缓存的 packets 中按顺序解码并确定性采样，返回 BGR 帧列表。
        
        必须在下一个 keyframe 解码之前调用，以保持 H.264 解码器参考帧状态。
        所有 packet 按顺序送入解码器（维护参考帧链），但只保留采样索引处的帧。
        """
        if not packets or not need_extra:
            return []
        # 确定采样索引
        total = len(packets)
        sample_set = set()
        if total <= vif_sample_n:
            sample_set = set(range(total))
        elif vif_sample_n == 1:
            # 单帧定中
            sample_set = {total // 2}
        else:
            # 均分
            step = total / vif_sample_n
            sample_set = {int(i * step + step/2) for i in range(vif_sample_n)}

        sampled: List[np.ndarray] = []
        max_needed = max(sample_set) + 1  # 只需解码到最后一个采样点
        # 抑制 H.264 解码 P/B 帧时的警告
        prev_level = av.logging.get_level()
        av.logging.set_level(av.logging.FATAL)
        # 按顺序解码到最后采样点为止，仅保留采样帧
        for idx in range(max_needed):
            pkt = packets[idx]
            try:
                decoded = stream.codec_context.decode(pkt)
                if decoded:
                    frame = decoded[0]
                    if idx in sample_set:
                        sampled.append(frame.to_ndarray(format="bgr24"))
            except Exception:
                pass
        av.logging.set_level(prev_level)
        return sampled

    for packet in container.demux(video_stream):
        if packet.size == 0:
            continue

        ts = _packet_ts(packet, video_stream)

        if intra_only:
            # MJPEG mode: group every mjpeg_gop_size frames into one GOP
            if frame_count == 0:
                # First frame of a new logical GOP — decode as keyframe
                pending_keyframe = _decode_keyframe(packet, video_stream)
                start_ts = ts

            buf.extend(bytes(packet))
            packet_sizes.append(packet.size)
            packet_pts.append(packet.pts)
            packet_dts.append(packet.dts)
            packet_keyframes.append(bool(packet.is_keyframe))
            frame_count += 1
            end_ts = ts

            if frame_count >= mjpeg_gop_size:
                gops.append(_build_gop(
                    gop_id, buf, start_ts, end_ts, frame_count, pending_keyframe,
                    stream_metadata=stream_metadata,
                    packet_sizes=packet_sizes,
                    packet_pts=packet_pts,
                    packet_dts=packet_dts,
                    packet_keyframes=packet_keyframes,
                ))
                gop_id += 1
                buf = bytearray()
                frame_count = 0
                pending_keyframe = None
                packet_sizes = []
                packet_pts = []
                packet_dts = []
                packet_keyframes = []
        else:
            # H.264/H.265 mode: split on keyframe boundaries
            if packet.is_keyframe:
                if buf and pending_keyframe is not None:
                    # ★ 关键：在解码新 keyframe 之前先采样上一个 GOP 的 P/B 帧
                    # 此时解码器的参考帧仍是上一个 GOP 的 I 帧
                    extra = _sample_extra_frames(gop_packets, video_stream)
                    gops.append(_build_gop(
                        gop_id, buf, start_ts, end_ts, frame_count,
                        pending_keyframe,
                        stream_metadata=stream_metadata,
                        packet_sizes=packet_sizes,
                        packet_pts=packet_pts,
                        packet_dts=packet_dts,
                        packet_keyframes=packet_keyframes,
                        extra_frames=extra,
                    ))
                    gop_id += 1

                # ★ 在 P/B 帧采样完成后，才解码新 keyframe
                new_keyframe = _decode_keyframe(packet, video_stream)
                pending_keyframe = new_keyframe
                buf = bytearray(bytes(packet))
                packet_sizes = [packet.size]
                packet_pts = [packet.pts]
                packet_dts = [packet.dts]
                packet_keyframes = [bool(packet.is_keyframe)]
                frame_count = 1
                start_ts = ts
                end_ts = ts
                gop_packets = []  # 重置 packet 缓存
            else:
                buf.extend(bytes(packet))
                packet_sizes.append(packet.size)
                packet_pts.append(packet.pts)
                packet_dts.append(packet.dts)
                packet_keyframes.append(bool(packet.is_keyframe))
                frame_count += 1
                end_ts = ts
                if need_extra:
                    gop_packets.append(packet)

    # Finalize the last GOP
    if buf and pending_keyframe is not None:
        extra = _sample_extra_frames(gop_packets, video_stream)
        gops.append(_build_gop(
            gop_id, buf, start_ts, end_ts, frame_count,
            pending_keyframe,
            stream_metadata=stream_metadata,
            packet_sizes=packet_sizes,
            packet_pts=packet_pts,
            packet_dts=packet_dts,
            packet_keyframes=packet_keyframes,
            extra_frames=extra,
        ))

    container.close()
    return gops


# ---------------------------------------------------------------------------
# Online mode – background thread that continuously splits a live stream
# ---------------------------------------------------------------------------

class GOPSplitter:
    """Continuously reads a live CCTV stream and emits GOPData via callback.

    For H.264/H.265 streams, GOP boundaries are detected by keyframes.
    For MJPEG streams (every frame is a keyframe), frames are grouped into
    logical GOPs of ``mjpeg_gop_size`` frames each.

    Usage::

        def handle_gop(gop: GOPData):
            print(gop.gop_id, gop.sha256_hash)

        splitter = GOPSplitter("https://cctv1.kctmc.nat.gov.tw/6e559e58/", handle_gop)
        splitter.start()
        # ... later ...
        splitter.stop()
    """

    def __init__(
        self,
        stream_url: str,
        on_gop: Callable[[GOPData], None],
        mjpeg_gop_size: int = DEFAULT_MJPEG_GOP_SIZE,
        queue_size: int = 128,
        ingest_mode: str = "direct",
    ):
        self.stream_url = stream_url
        self.on_gop = on_gop
        self.mjpeg_gop_size = mjpeg_gop_size
        self.queue_size = max(1, int(queue_size))
        self.ingest_mode = ingest_mode
        self._stop_event = threading.Event()
        self._ingest_thread: Optional[threading.Thread] = None
        self._build_thread: Optional[threading.Thread] = None
        self._build_queue: "queue.Queue[PendingGOP]" = queue.Queue(maxsize=self.queue_size)
        self._next_gop_id = 0
        self._session_seq = 0
        self._discarded_partial_gops = 0
        self._reconnect_count = 0
        self._last_valid_gop_at: Optional[float] = None
        self._last_backpressure_log_at = 0.0

    # -- public API ---------------------------------------------------------

    def start(self):
        """Start the background splitter thread."""
        if self._ingest_thread is not None and self._ingest_thread.is_alive():
            print("[GOP_SPLITTER] Already running")
            return
        prewarm_gop_processors()
        self._stop_event.clear()
        self._build_thread = threading.Thread(target=self._run_build_loop, daemon=True)
        self._ingest_thread = threading.Thread(target=self._run_ingest_loop, daemon=True)
        self._build_thread.start()
        self._ingest_thread.start()
        print(f"[GOP_SPLITTER] Started for {self.stream_url}")

    def stop(self):
        """Signal the background thread to stop."""
        self._stop_event.set()
        if self._ingest_thread is not None:
            self._ingest_thread.join(timeout=10)
        if self._build_thread is not None:
            self._build_thread.join(timeout=10)
        print("[GOP_SPLITTER] Stopped")

    def get_runtime_stats(self) -> Dict[str, Optional[Union[float, int, str]]]:
        oldest_pending_age = None
        with self._build_queue.mutex:
            pending = list(self._build_queue.queue)
        if pending:
            oldest_pending_age = max(time.time() - pending[0].queued_at, 0.0)
        return {
            "splitter_queue_depth": self._build_queue.qsize(),
            "oldest_pending_age_seconds": oldest_pending_age,
            "discarded_partial_gops": self._discarded_partial_gops,
            "reconnect_count": self._reconnect_count,
            "last_valid_gop_at": self._last_valid_gop_at,
            "ingest_mode": self.ingest_mode,
        }

    # -- internals ----------------------------------------------------------

    def _open_stream(self) -> av.container.InputContainer:
        """Open the stream with protocol-appropriate options."""
        options = {}
        url = self.stream_url
        if url.startswith("rtsp://"):
            options["rtsp_transport"] = "tcp"
        return av.open(url, options=options)

    def _run_ingest_loop(self):
        """Main loop: connect -> demux -> enqueue pending GOPs -> reconnect on failure."""
        while not self._stop_event.is_set():
            try:
                self._session_seq += 1
                self._process_stream()
            except Exception as e:
                print(f"[GOP_SPLITTER] Stream error: {e}")
            finally:
                if not self._stop_event.is_set():
                    self._reconnect_count += 1
                    print("[GOP_SPLITTER] Reconnecting in 3 seconds...")
                    self._stop_event.wait(timeout=3)

    def _run_build_loop(self):
        """Build heavyweight GOP fingerprints on a separate worker thread."""
        while not self._stop_event.is_set() or not self._build_queue.empty():
            try:
                pending = self._build_queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                gop = _build_gop(
                    pending.gop_id,
                    bytearray(pending.raw_bytes),
                    pending.start_ts,
                    pending.end_ts,
                    pending.frame_count,
                    pending.keyframe_frame,
                    stream_metadata=pending.stream_metadata,
                    packet_sizes=pending.packet_sizes,
                    packet_pts=pending.packet_pts,
                    packet_dts=pending.packet_dts,
                    packet_keyframes=pending.packet_keyframes,
                )
                try:
                    self.on_gop(gop)
                except Exception as e:
                    print(f"[GOP_SPLITTER] Callback error on GOP {gop.gop_id}: {e}")
            finally:
                self._build_queue.task_done()

    def _is_valid_pending_gop(
        self,
        raw_bytes: bytes,
        start_ts: float,
        end_ts: float,
        frame_count: int,
        packet_pts: List[Optional[int]],
    ) -> bool:
        return (
            bool(raw_bytes)
            and frame_count > 1
            and len(packet_pts) > 1
            and end_ts > start_ts
        )

    def _enqueue_pending_gop(
        self,
        raw_bytes: bytes,
        start_ts: float,
        end_ts: float,
        frame_count: int,
        keyframe_frame: np.ndarray,
        stream_metadata: Dict[str, Optional[object]],
        packet_sizes: List[int],
        packet_pts: List[Optional[int]],
        packet_dts: List[Optional[int]],
        packet_keyframes: List[bool],
    ):
        if not self._is_valid_pending_gop(raw_bytes, start_ts, end_ts, frame_count, packet_pts):
            self._discarded_partial_gops += 1
            print(
                "[GOP_SPLITTER] Dropped partial GOP "
                f"(frames={frame_count}, packets={len(packet_pts)}, start={start_ts:.3f}, end={end_ts:.3f})"
            )
            return

        pending = PendingGOP(
            session_seq=self._session_seq,
            gop_id=self._next_gop_id,
            raw_bytes=raw_bytes,
            start_ts=start_ts,
            end_ts=end_ts,
            frame_count=frame_count,
            keyframe_frame=keyframe_frame,
            stream_metadata=dict(stream_metadata),
            packet_sizes=list(packet_sizes),
            packet_pts=list(packet_pts),
            packet_dts=list(packet_dts),
            packet_keyframes=list(packet_keyframes),
            queued_at=time.time(),
        )
        self._next_gop_id += 1
        while not self._stop_event.is_set():
            try:
                self._build_queue.put(pending, timeout=0.5)
                self._last_valid_gop_at = time.time()
                return
            except queue.Full:
                now = time.time()
                if (now - self._last_backpressure_log_at) >= 5:
                    self._last_backpressure_log_at = now
                    print(
                        "[GOP_SPLITTER] Build queue backpressure: "
                        f"depth={self._build_queue.qsize()}/{self.queue_size}"
                    )

    def _process_stream(self):
        """Process one connection session until EOF or error."""
        container = self._open_stream()
        video_stream = container.streams.video[0]
        intra_only = _is_intra_only(video_stream)

        codec_name = video_stream.codec_context.name
        if intra_only:
            print(f"[GOP_SPLITTER] Intra-only codec ({codec_name}), "
                  f"grouping every {self.mjpeg_gop_size} frames as one logical GOP")
        else:
            print(f"[GOP_SPLITTER] Inter-frame codec ({codec_name}), "
                  f"splitting on keyframe boundaries")

        buf = bytearray()
        frame_count = 0
        start_ts = 0.0
        end_ts = 0.0
        pending_keyframe: Optional[np.ndarray] = None
        stream_metadata = _extract_stream_metadata(video_stream)
        packet_sizes: List[int] = []
        packet_pts: List[Optional[int]] = []
        packet_dts: List[Optional[int]] = []
        packet_keyframes: List[bool] = []

        try:
            for packet in container.demux(video_stream):
                if self._stop_event.is_set():
                    break

                if packet.size == 0:
                    continue

                ts = _packet_ts(packet, video_stream)

                if intra_only:
                    # MJPEG mode: group N frames into one logical GOP
                    if frame_count == 0:
                        pending_keyframe = _decode_keyframe(packet, video_stream)
                        start_ts = ts

                    buf.extend(bytes(packet))
                    packet_sizes.append(packet.size)
                    packet_pts.append(packet.pts)
                    packet_dts.append(packet.dts)
                    packet_keyframes.append(bool(packet.is_keyframe))
                    frame_count += 1
                    end_ts = ts

                    if frame_count >= self.mjpeg_gop_size:
                        self._enqueue_pending_gop(
                            bytes(buf), start_ts, end_ts, frame_count, pending_keyframe,
                            stream_metadata, packet_sizes, packet_pts, packet_dts, packet_keyframes,
                        )
                        buf = bytearray()
                        frame_count = 0
                        pending_keyframe = None
                        packet_sizes = []
                        packet_pts = []
                        packet_dts = []
                        packet_keyframes = []
                else:
                    # H.264/H.265 mode: split on keyframe boundaries
                    if packet.is_keyframe:
                        new_keyframe = _decode_keyframe(packet, video_stream)

                        if buf and pending_keyframe is not None:
                            self._enqueue_pending_gop(
                                bytes(buf), start_ts, end_ts, frame_count, pending_keyframe,
                                stream_metadata, packet_sizes, packet_pts, packet_dts, packet_keyframes,
                            )

                        pending_keyframe = new_keyframe
                        buf = bytearray(bytes(packet))
                        packet_sizes = [packet.size]
                        packet_pts = [packet.pts]
                        packet_dts = [packet.dts]
                        packet_keyframes = [bool(packet.is_keyframe)]
                        frame_count = 1
                        start_ts = ts
                        end_ts = ts
                    else:
                        buf.extend(bytes(packet))
                        packet_sizes.append(packet.size)
                        packet_pts.append(packet.pts)
                        packet_dts.append(packet.dts)
                        packet_keyframes.append(bool(packet.is_keyframe))
                        frame_count += 1
                        end_ts = ts

            # Stream ended – emit final partial GOP
            if buf and pending_keyframe is not None:
                self._enqueue_pending_gop(
                    bytes(buf), start_ts, end_ts, frame_count, pending_keyframe,
                    stream_metadata, packet_sizes, packet_pts, packet_dts, packet_keyframes,
                )

        finally:
            container.close()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _print_gop_summary(gop: GOPData):
    """Print a single-line summary of a GOP (used by CLI mode)."""
    print(
        f"  GOP {gop.gop_id:>4d}  |  "
        f"{gop.start_time:>8.3f}s - {gop.end_time:>8.3f}s  |  "
        f"frames={gop.frame_count:<4d}  |  "
        f"size={gop.byte_size:>10,} bytes  |  "
        f"sha256={gop.sha256_hash[:16]}...  |  "
        f"keyframe={gop.keyframe_frame.shape}"
    )


def main():
    parser = argparse.ArgumentParser(description="GOP-level video splitter")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=str, help="Local video file path")
    group.add_argument("--stream", type=str, help="Live CCTV stream URL")
    parser.add_argument(
        "--mjpeg-gop-size",
        type=int,
        default=DEFAULT_MJPEG_GOP_SIZE,
        help=f"Frames per logical GOP for MJPEG streams (default: {DEFAULT_MJPEG_GOP_SIZE})",
    )
    args = parser.parse_args()

    if args.file:
        # Offline mode
        path = Path(args.file).expanduser().resolve()
        if not path.exists():
            print(f"[GOP_SPLITTER] File not found: {path}")
            return

        print(f"[GOP_SPLITTER] Splitting file: {path}")
        gops = split_gops(str(path), mjpeg_gop_size=args.mjpeg_gop_size)
        print(f"[GOP_SPLITTER] Total GOPs: {len(gops)}\n")
        for gop in gops:
            _print_gop_summary(gop)
    else:
        # Online mode
        print(f"[GOP_SPLITTER] Connecting to stream: {args.stream}")
        print("[GOP_SPLITTER] Press Ctrl+C to stop\n")

        splitter = GOPSplitter(args.stream, _print_gop_summary, mjpeg_gop_size=args.mjpeg_gop_size)
        splitter.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[GOP_SPLITTER] Shutting down...")
            splitter.stop()


if __name__ == "__main__":
    main()
