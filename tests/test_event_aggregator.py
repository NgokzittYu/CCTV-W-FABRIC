"""Tests for event aggregation engine."""
from services.event_aggregator import bbox_iou, resolve_class_name, EventAggregator


def test_bbox_iou_no_overlap():
    """Test IoU with no overlap."""
    box1 = (0, 0, 10, 10)
    box2 = (20, 20, 30, 30)
    assert bbox_iou(box1, box2) == 0.0


def test_bbox_iou_full_overlap():
    """Test IoU with full overlap."""
    box1 = (0, 0, 10, 10)
    box2 = (0, 0, 10, 10)
    assert bbox_iou(box1, box2) == 1.0


def test_bbox_iou_partial_overlap():
    """Test IoU with partial overlap."""
    box1 = (0, 0, 10, 10)
    box2 = (5, 5, 15, 15)
    iou = bbox_iou(box1, box2)
    assert 0 < iou < 1


def test_resolve_class_name():
    """Test class name resolution."""
    class MockModel:
        names = {0: "person", 1: "car"}

    model = MockModel()
    assert resolve_class_name(0, model) == "person"
    assert resolve_class_name(1, model) == "car"
    assert resolve_class_name(99, model) == "class_99"


def test_event_aggregator_initialization():
    """Test EventAggregator initialization."""
    agg = EventAggregator(min_frames=3, max_missed_frames=5)
    assert agg.min_frames == 3
    assert agg.max_missed_frames == 5
    assert len(agg.active_events) == 0
