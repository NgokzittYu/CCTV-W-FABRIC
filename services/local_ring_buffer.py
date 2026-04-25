"""Local ffmpeg-backed ring buffer for unstable live sources."""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, Optional, Union

logger = logging.getLogger(__name__)


class LocalRingBufferManager:
    """Mirror a remote live source into a local rolling HLS playlist."""

    def __init__(
        self,
        source_url: str,
        output_dir: str | Path,
        *,
        segment_seconds: int = 1,
        retention_seconds: int = 3600,
    ):
        self.source_url = source_url
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.segment_seconds = max(1, int(segment_seconds))
        self.retention_seconds = max(self.segment_seconds * 3, int(retention_seconds))
        self.playlist_path = self.output_dir / "live.m3u8"
        self._process: Optional[subprocess.Popen] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_log_line: Optional[str] = None

    @property
    def ingest_mode(self) -> str:
        return "buffered"

    def _cleanup_output(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        for path in self.output_dir.iterdir():
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass

    def _build_command(self) -> list[str]:
        hls_list_size = max(8, self.retention_seconds // self.segment_seconds)
        segment_pattern = str(self.output_dir / "segment_%09d.ts")
        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-nostats",
            "-nostdin",
            "-fflags",
            "+discardcorrupt",
            "-reconnect",
            "1",
            "-reconnect_streamed",
            "1",
            "-reconnect_at_eof",
            "1",
            "-reconnect_on_network_error",
            "1",
            "-reconnect_delay_max",
            "5",
            "-rw_timeout",
            "10000000",
            "-i",
            self.source_url,
            "-an",
            "-c",
            "copy",
            "-f",
            "hls",
            "-hls_time",
            str(self.segment_seconds),
            "-hls_list_size",
            str(hls_list_size),
            "-hls_flags",
            "append_list+delete_segments+program_date_time+independent_segments+omit_endlist",
            "-hls_segment_type",
            "mpegts",
            "-hls_segment_filename",
            segment_pattern,
            str(self.playlist_path),
        ]

    def _stderr_pump(self):
        if not self._process or not self._process.stderr:
            return
        for line in self._process.stderr:
            if self._stop_event.is_set():
                break
            text = line.strip()
            if not text:
                continue
            self._last_log_line = text
            logger.warning("[RING_BUFFER] ffmpeg: %s", text)

    def start(self):
        if self._process and self._process.poll() is None:
            return
        self._cleanup_output()
        self._stop_event.clear()
        cmd = self._build_command()
        logger.info("[RING_BUFFER] Starting local buffer: %s", " ".join(cmd))
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._stderr_thread = threading.Thread(target=self._stderr_pump, daemon=True)
        self._stderr_thread.start()

    def stop(self):
        self._stop_event.set()
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=5)
        self._process = None

    def wait_until_ready(self, timeout_seconds: float = 20.0) -> bool:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            if self._process and self._process.poll() is not None:
                return False
            if self.playlist_path.exists():
                try:
                    text = self.playlist_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    text = ""
                if "#EXTM3U" in text and "#EXTINF:" in text:
                    return True
            time.sleep(0.5)
        return False

    def get_stats(self) -> Dict[str, Optional[Union[float, int, str, bool]]]:
        segment_count = len(list(self.output_dir.glob("segment_*.ts"))) if self.output_dir.exists() else 0
        last_segment_mtime = None
        newest_segment = None
        if self.output_dir.exists():
            segments = list(self.output_dir.glob("segment_*.ts"))
            if segments:
                newest_segment = max(segments, key=lambda p: p.stat().st_mtime)
                last_segment_mtime = newest_segment.stat().st_mtime
        return {
            "enabled": True,
            "running": bool(self._process and self._process.poll() is None),
            "playlist_path": str(self.playlist_path),
            "segment_count": segment_count,
            "last_segment_mtime": last_segment_mtime,
            "stale_seconds": (time.time() - last_segment_mtime) if last_segment_mtime else None,
            "last_log_line": self._last_log_line,
        }
