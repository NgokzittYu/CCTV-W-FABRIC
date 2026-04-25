"""Helpers for deriving inclusive GOP timing from packet metadata."""

from typing import Iterable, Optional, Sequence, Tuple


def infer_frame_interval_seconds(
    packet_pts: Optional[Sequence[Optional[int]]],
    time_base_num: Optional[int],
    time_base_den: Optional[int],
    frame_rate_num: Optional[int] = None,
    frame_rate_den: Optional[int] = None,
) -> Optional[float]:
    """Infer one frame interval in seconds from packet PTS metadata.

    PyAV packet timestamps represent packet presentation instants. When a GOP
    spans N packets/frames, the raw ``last_pts - first_pts`` delta undercounts
    the actual covered duration by one frame interval. We infer that interval
    from the median positive PTS delta, with frame rate as fallback.
    """
    pts_values = [int(value) for value in (packet_pts or []) if value is not None]
    if len(pts_values) >= 2 and time_base_num and time_base_den:
        deltas = sorted(
            current - previous
            for previous, current in zip(pts_values, pts_values[1:])
            if current > previous
        )
        if deltas:
            median_delta = deltas[len(deltas) // 2]
            return float(median_delta * time_base_num / time_base_den)

    if frame_rate_num and frame_rate_den and frame_rate_num > 0:
        return float(frame_rate_den / frame_rate_num)

    return None


def normalize_gop_bounds(
    start_time: float,
    end_time: float,
    *,
    packet_pts: Optional[Sequence[Optional[int]]] = None,
    time_base_num: Optional[int] = None,
    time_base_den: Optional[int] = None,
    frame_rate_num: Optional[int] = None,
    frame_rate_den: Optional[int] = None,
) -> Tuple[float, float, float]:
    """Return inclusive GOP bounds and duration in seconds.

    ``start_time`` / ``end_time`` from the splitter currently reflect the first
    and last packet PTS. For a GOP with multiple packets, the actual covered
    duration should include the final frame interval as well.
    """
    start = float(start_time)
    raw_duration = max(float(end_time) - start, 0.0)
    frame_interval = infer_frame_interval_seconds(
        packet_pts,
        time_base_num,
        time_base_den,
        frame_rate_num,
        frame_rate_den,
    )

    if frame_interval is None:
        duration = raw_duration
    elif packet_pts and len([value for value in packet_pts if value is not None]) >= 2:
        duration = raw_duration + frame_interval
    else:
        duration = max(raw_duration, frame_interval)

    end = start + max(duration, 0.0)
    return start, end, max(duration, 0.0)
