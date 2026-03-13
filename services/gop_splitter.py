"""GOP-level video stream splitter using PyAV.

Splits a live CCTV stream (or local MP4 file) into GOP segments by detecting
keyframe boundaries at the packet level. Each GOP's raw encoded bytes are
SHA-256 hashed for content-addressable evidence integrity.

For intra-only codecs (MJPEG) where every frame is a keyframe, packets are
grouped into logical GOPs of a configurable size (default 25 frames).
"""
import argparse
import hashlib
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

import av
import numpy as np

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
    """Decode the keyframe packet and return a BGR numpy array."""
    codec_ctx = av.CodecContext.create(stream.codec_context.name, "r")
    codec_ctx.extradata = stream.codec_context.extradata
    codec_ctx.width = stream.codec_context.width
    codec_ctx.height = stream.codec_context.height
    codec_ctx.pix_fmt = stream.codec_context.pix_fmt

    frames = codec_ctx.decode(packet)
    if frames:
        return frames[0].to_ndarray(format="bgr24")

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
) -> GOPData:
    raw = bytes(buf)
    return GOPData(
        gop_id=gop_id,
        raw_bytes=raw,
        sha256_hash=hashlib.sha256(raw).hexdigest(),
        start_time=start_ts,
        end_time=end_ts,
        frame_count=frame_count,
        byte_size=len(raw),
        keyframe_frame=keyframe_frame,
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

    if intra_only:
        print(f"[GOP_SPLITTER] Intra-only codec ({video_stream.codec_context.name}), "
              f"grouping every {mjpeg_gop_size} frames as one logical GOP")

    gops: List[GOPData] = []
    gop_id = 0

    buf = bytearray()
    frame_count = 0
    start_ts = 0.0
    end_ts = 0.0
    pending_keyframe: Optional[np.ndarray] = None

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
            frame_count += 1
            end_ts = ts

            if frame_count >= mjpeg_gop_size:
                gops.append(_build_gop(gop_id, buf, start_ts, end_ts, frame_count, pending_keyframe))
                gop_id += 1
                buf = bytearray()
                frame_count = 0
                pending_keyframe = None
        else:
            # H.264/H.265 mode: split on keyframe boundaries
            if packet.is_keyframe:
                new_keyframe = _decode_keyframe(packet, video_stream)

                if buf and pending_keyframe is not None:
                    gops.append(_build_gop(gop_id, buf, start_ts, end_ts, frame_count, pending_keyframe))
                    gop_id += 1

                pending_keyframe = new_keyframe
                buf = bytearray(bytes(packet))
                frame_count = 1
                start_ts = ts
                end_ts = ts
            else:
                buf.extend(bytes(packet))
                frame_count += 1
                end_ts = ts

    # Finalize the last GOP
    if buf and pending_keyframe is not None:
        gops.append(_build_gop(gop_id, buf, start_ts, end_ts, frame_count, pending_keyframe))

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
    ):
        self.stream_url = stream_url
        self.on_gop = on_gop
        self.mjpeg_gop_size = mjpeg_gop_size
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._next_gop_id = 0

    # -- public API ---------------------------------------------------------

    def start(self):
        """Start the background splitter thread."""
        if self._thread is not None and self._thread.is_alive():
            print("[GOP_SPLITTER] Already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        print(f"[GOP_SPLITTER] Started for {self.stream_url}")

    def stop(self):
        """Signal the background thread to stop."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        print("[GOP_SPLITTER] Stopped")

    # -- internals ----------------------------------------------------------

    def _open_stream(self) -> av.container.InputContainer:
        """Open the stream with protocol-appropriate options."""
        options = {}
        url = self.stream_url
        if url.startswith("rtsp://"):
            options["rtsp_transport"] = "tcp"
        return av.open(url, options=options)

    def _run(self):
        """Main loop: connect -> demux -> emit GOPs -> reconnect on failure."""
        while not self._stop_event.is_set():
            try:
                self._process_stream()
            except Exception as e:
                print(f"[GOP_SPLITTER] Stream error: {e}")
            finally:
                if not self._stop_event.is_set():
                    print("[GOP_SPLITTER] Reconnecting in 3 seconds...")
                    self._stop_event.wait(timeout=3)

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
                    frame_count += 1
                    end_ts = ts

                    if frame_count >= self.mjpeg_gop_size:
                        self._emit_gop(buf, start_ts, end_ts, frame_count, pending_keyframe)
                        buf = bytearray()
                        frame_count = 0
                        pending_keyframe = None
                else:
                    # H.264/H.265 mode: split on keyframe boundaries
                    if packet.is_keyframe:
                        new_keyframe = _decode_keyframe(packet, video_stream)

                        if buf and pending_keyframe is not None:
                            self._emit_gop(buf, start_ts, end_ts, frame_count, pending_keyframe)

                        pending_keyframe = new_keyframe
                        buf = bytearray(bytes(packet))
                        frame_count = 1
                        start_ts = ts
                        end_ts = ts
                    else:
                        buf.extend(bytes(packet))
                        frame_count += 1
                        end_ts = ts

            # Stream ended – emit final partial GOP
            if buf and pending_keyframe is not None:
                self._emit_gop(buf, start_ts, end_ts, frame_count, pending_keyframe)

        finally:
            container.close()

    def _emit_gop(
        self,
        buf: bytearray,
        start_ts: float,
        end_ts: float,
        frame_count: int,
        keyframe_frame: np.ndarray,
    ):
        """Build GOPData and invoke the callback."""
        gop = _build_gop(self._next_gop_id, buf, start_ts, end_ts, frame_count, keyframe_frame)
        self._next_gop_id += 1

        try:
            self.on_gop(gop)
        except Exception as e:
            print(f"[GOP_SPLITTER] Callback error on GOP {gop.gop_id}: {e}")


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
