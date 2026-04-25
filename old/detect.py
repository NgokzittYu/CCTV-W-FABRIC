import argparse
import json
import os
import time

import cv2
from ultralytics import YOLO

from config import SETTINGS

DEFAULT_STREAM_PAGE = SETTINGS.video_source
# COCO class ids: person, bicycle, car, motorcycle, bus, truck
ROAD_TARGET_CLASS_IDS = SETTINGS.road_target_class_ids


def resolve_stream_source(raw_source: str) -> str:
    source = raw_source.strip()
    lower = source.lower()
    media_exts = (".m3u8", ".mp4", ".ts", ".avi", ".mov", ".mkv", ".rtsp")
    if lower.endswith(media_exts):
        return source

    if lower.startswith(("http://", "https://")):
        base = source.rstrip("/")
        candidates = [
            source,
            f"{base}/index.m3u8",
            f"{base}/playlist.m3u8",
            f"{base}/live.m3u8",
        ]
        for candidate in candidates:
            cap = cv2.VideoCapture(candidate)
            ok = cap.isOpened()
            cap.release()
            if ok:
                print(f"[INFO] 使用视频源: {candidate}")
                return candidate
        print(
            "[WARN] 无法自动解析网页地址为可读流，继续尝试原始地址。"
            "若失败请改为直接传入 .m3u8 URL。"
        )
    return source


def open_capture(source: str) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频源: {source}")
    return cap


def main():
    parser = argparse.ArgumentParser(description="YOLO detect from local file or live stream")
    parser.add_argument("--source", default=DEFAULT_STREAM_PAGE, help="Video path/URL/stream URL")
    parser.add_argument("--model", default=SETTINGS.detect_default_model, help="Model path")
    parser.add_argument(
        "--conf",
        type=float,
        default=SETTINGS.detect_confidence_threshold,
        help="Confidence threshold",
    )
    parser.add_argument(
        "--save-every",
        type=int,
        default=SETTINGS.detect_save_every,
        help="Save JSON every N frames",
    )
    parser.add_argument(
        "--output-dir",
        default=SETTINGS.detect_output_dir,
        help="Output evidence directory",
    )
    parser.add_argument("--imgsz", type=int, default=SETTINGS.detect_imgsz, help="Inference image size")
    parser.add_argument("--save-frame", action="store_true", help="Save raw and annotated frame images")
    parser.add_argument("--max-frames", type=int, default=0, help="Stop after N frames (0 = unlimited)")
    parser.add_argument(
        "--reconnect-every",
        type=int,
        default=SETTINGS.detect_reconnect_every,
        help="Reconnect stream after N consecutive read failures",
    )
    parser.add_argument(
        "--retry-sleep",
        type=float,
        default=SETTINGS.detect_retry_sleep,
        help="Sleep seconds on transient frame read failure",
    )
    parser.add_argument(
        "--reconnect-sleep",
        type=float,
        default=SETTINGS.detect_reconnect_sleep,
        help="Sleep seconds before reconnect",
    )
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    model = YOLO(args.model)
    source = resolve_stream_source(args.source)
    cap = open_capture(source)
    frame_idx = 0
    consecutive_failures = 0
    reconnect_count = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                consecutive_failures += 1
                if consecutive_failures >= args.reconnect_every:
                    reconnect_count += 1
                    print(f"[WARN] 连续读帧失败 {consecutive_failures} 次，尝试重连第 {reconnect_count} 次")
                    cap.release()
                    time.sleep(args.reconnect_sleep)
                    cap = open_capture(source)
                    consecutive_failures = 0
                else:
                    time.sleep(args.retry_sleep)
                continue

            consecutive_failures = 0
            result = model.predict(
                frame,
                conf=args.conf,
                imgsz=args.imgsz,
                classes=ROAD_TARGET_CLASS_IDS,
                verbose=False,
            )[0]

            if frame_idx % args.save_every == 0:
                detection = {
                    "event_id": f"event_{frame_idx:04d}",
                    "timestamp": time.time(),
                    "source": source,
                    "frame": frame_idx,
                    "detections": [
                        {"class": model.names[int(c)], "confidence": float(conf)}
                        for c, conf in zip(result.boxes.cls, result.boxes.conf)
                    ],
                }

                filename = os.path.join(args.output_dir, f"event_{frame_idx:04d}.json")
                with open(filename, "w", encoding="utf-8") as f:
                    json.dump(detection, f, indent=2, ensure_ascii=False)

                if args.save_frame:
                    raw_img = os.path.join(args.output_dir, f"event_{frame_idx:04d}.jpg")
                    ann_img = os.path.join(args.output_dir, f"event_{frame_idx:04d}_ann.jpg")
                    cv2.imwrite(raw_img, frame)
                    cv2.imwrite(ann_img, result.plot())
                print(f"[OK] 保存: {filename} ({len(detection['detections'])} objects)")

            frame_idx += 1
            if args.max_frames > 0 and frame_idx >= args.max_frames:
                break
    finally:
        cap.release()

    print(f"[DONE] 检测完成，总帧数={frame_idx}, 重连次数={reconnect_count}")


if __name__ == "__main__":
    main()
