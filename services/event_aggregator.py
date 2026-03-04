"""Event aggregation engine for combining detection events."""
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


def bbox_iou(box1: Tuple[float, float, float, float], box2: Tuple[float, float, float, float]) -> float:
    """Calculate IoU (Intersection over Union) between two bounding boxes."""
    x1_min, y1_min, x1_max, y1_max = box1
    x2_min, y2_min, x2_max, y2_max = box2

    inter_xmin = max(x1_min, x2_min)
    inter_ymin = max(y1_min, y2_min)
    inter_xmax = min(x1_max, x2_max)
    inter_ymax = min(y1_max, y2_max)

    if inter_xmax <= inter_xmin or inter_ymax <= inter_ymin:
        return 0.0

    inter_area = (inter_xmax - inter_xmin) * (inter_ymax - inter_ymin)
    box1_area = (x1_max - x1_min) * (y1_max - y1_min)
    box2_area = (x2_max - x2_min) * (y2_max - y2_min)
    union_area = box1_area + box2_area - inter_area

    return inter_area / union_area if union_area > 0 else 0.0


def resolve_class_name(class_id: int, model) -> str:
    """Resolve class name from class ID using model names."""
    if hasattr(model, "names") and isinstance(model.names, dict):
        return model.names.get(class_id, f"class_{class_id}")
    return f"class_{class_id}"


@dataclass
class AggregatedEvent:
    """Represents an aggregated detection event."""
    track_id: int
    class_id: int
    class_name: str
    first_seen: float
    last_seen: float
    frame_count: int = 0
    missed_frames: int = 0
    bbox_history: List[Tuple[float, float, float, float]] = field(default_factory=list)
    conf_history: List[float] = field(default_factory=list)

    def update(self, bbox: Tuple[float, float, float, float], conf: float, timestamp: float):
        """Update event with new detection."""
        self.last_seen = timestamp
        self.frame_count += 1
        self.missed_frames = 0
        self.bbox_history.append(bbox)
        self.conf_history.append(conf)

    def increment_missed(self):
        """Increment missed frame counter."""
        self.missed_frames += 1

    def get_average_bbox(self) -> Tuple[float, float, float, float]:
        """Calculate average bounding box."""
        if not self.bbox_history:
            return (0.0, 0.0, 0.0, 0.0)
        n = len(self.bbox_history)
        avg_x1 = sum(b[0] for b in self.bbox_history) / n
        avg_y1 = sum(b[1] for b in self.bbox_history) / n
        avg_x2 = sum(b[2] for b in self.bbox_history) / n
        avg_y2 = sum(b[3] for b in self.bbox_history) / n
        return (avg_x1, avg_y1, avg_x2, avg_y2)

    def get_average_confidence(self) -> float:
        """Calculate average confidence."""
        if not self.conf_history:
            return 0.0
        return sum(self.conf_history) / len(self.conf_history)


class EventAggregator:
    """Aggregates detection events over time."""

    def __init__(
        self,
        min_frames: int = 3,
        max_missed_frames: int = 5,
        iou_threshold: float = 0.3,
        window_seconds: float = 10.0,
    ):
        self.min_frames = min_frames
        self.max_missed_frames = max_missed_frames
        self.iou_threshold = iou_threshold
        self.window_seconds = window_seconds
        self.active_events: Dict[int, AggregatedEvent] = {}
        self.next_track_id = 1

    def process_detections(
        self, detections: List[Dict], timestamp: float, model
    ) -> List[AggregatedEvent]:
        """
        Process new detections and return completed events.

        Args:
            detections: List of detection dicts with 'box', 'conf', 'cls'
            timestamp: Current timestamp
            model: YOLO model for class name resolution

        Returns:
            List of completed aggregated events
        """
        current_boxes = []
        for det in detections:
            box = det.get("box", {})
            bbox = (
                float(box.get("x1", 0)),
                float(box.get("y1", 0)),
                float(box.get("x2", 0)),
                float(box.get("y2", 0)),
            )
            conf = float(det.get("conf", 0))
            class_id = int(det.get("cls", 0))
            class_name = resolve_class_name(class_id, model)
            current_boxes.append((bbox, conf, class_id, class_name))

        matched_tracks = set()
        for bbox, conf, class_id, class_name in current_boxes:
            best_iou = 0.0
            best_track_id = None

            for track_id, event in self.active_events.items():
                if event.class_id != class_id:
                    continue
                if event.bbox_history:
                    last_bbox = event.bbox_history[-1]
                    iou = bbox_iou(bbox, last_bbox)
                    if iou > best_iou and iou >= self.iou_threshold:
                        best_iou = iou
                        best_track_id = track_id

            if best_track_id is not None:
                self.active_events[best_track_id].update(bbox, conf, timestamp)
                matched_tracks.add(best_track_id)
            else:
                new_event = AggregatedEvent(
                    track_id=self.next_track_id,
                    class_id=class_id,
                    class_name=class_name,
                    first_seen=timestamp,
                    last_seen=timestamp,
                )
                new_event.update(bbox, conf, timestamp)
                self.active_events[self.next_track_id] = new_event
                matched_tracks.add(self.next_track_id)
                self.next_track_id += 1

        for track_id in list(self.active_events.keys()):
            if track_id not in matched_tracks:
                self.active_events[track_id].increment_missed()

        completed = []
        for track_id in list(self.active_events.keys()):
            event = self.active_events[track_id]
            should_complete = False

            if event.missed_frames > self.max_missed_frames:
                should_complete = True
            elif timestamp - event.first_seen > self.window_seconds:
                should_complete = True

            if should_complete and event.frame_count >= self.min_frames:
                completed.append(event)
                del self.active_events[track_id]
            elif should_complete:
                del self.active_events[track_id]

        return completed

    def flush_all(self) -> List[AggregatedEvent]:
        """Flush all active events."""
        completed = [
            event for event in self.active_events.values()
            if event.frame_count >= self.min_frames
        ]
        self.active_events.clear()
        return completed

    def update(self, boxes, class_names) -> List[Dict]:
        """Update aggregator with YOLO detection boxes and return completed events as dicts."""
        timestamp = time.time()
        detections = []

        if boxes is not None and len(boxes) > 0:
            for box in boxes:
                det = {
                    "box": {
                        "x1": float(box.xyxy[0][0]),
                        "y1": float(box.xyxy[0][1]),
                        "x2": float(box.xyxy[0][2]),
                        "y2": float(box.xyxy[0][3]),
                    },
                    "conf": float(box.conf[0]),
                    "cls": int(box.cls[0]),
                }
                detections.append(det)

        class Model:
            def __init__(self, names):
                self.names = names

        model = Model(class_names)
        completed = self.process_detections(detections, timestamp, model)

        result = []
        for event in completed:
            avg_bbox = event.get_average_bbox()
            result.append({
                "event_id": f"event_{int(event.first_seen * 1000)}_{event.track_id}",
                "timestamp": int(event.first_seen),
                "top_class": event.class_name,
                "frame_count": event.frame_count,
                "duration": round(event.last_seen - event.first_seen, 2),
                "detections": [{
                    "class": event.class_name,
                    "confidence": round(event.get_average_confidence(), 3),
                    "bbox": {
                        "x1": round(avg_bbox[0], 1),
                        "y1": round(avg_bbox[1], 1),
                        "x2": round(avg_bbox[2], 1),
                        "y2": round(avg_bbox[3], 1),
                    }
                }]
            })

        return result
