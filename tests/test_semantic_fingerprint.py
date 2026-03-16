"""
Unit tests for semantic fingerprint extraction.
"""
import numpy as np
import pytest
from services.semantic_fingerprint import SemanticExtractor, SemanticFingerprint


class TestSemanticExtractor:
    """Test SemanticExtractor class."""

    def test_singleton_pattern(self):
        """Test that get_instance returns the same instance."""
        extractor1 = SemanticExtractor.get_instance()
        extractor2 = SemanticExtractor.get_instance()
        assert extractor1 is extractor2

    def test_extract_with_synthetic_frame(self):
        """Test extraction with a synthetic frame."""
        # Create a synthetic BGR frame (480x640x3)
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        extractor = SemanticExtractor.get_instance()
        result = extractor.extract(
            keyframe_frame=frame,
            gop_id=1,
            start_time=1234567890.0
        )

        # Should return a valid fingerprint (even if no objects detected)
        assert result is not None
        assert isinstance(result, SemanticFingerprint)
        assert result.gop_id == 1
        assert result.timestamp.startswith("20")  # ISO 8601 format
        assert isinstance(result.objects, dict)
        assert isinstance(result.total_count, int)
        assert result.total_count >= 0
        assert isinstance(result.json_str, str)
        assert isinstance(result.semantic_hash, str)
        assert len(result.semantic_hash) == 64  # SHA-256 hex

    def test_deterministic_json(self):
        """Test that same input produces same JSON and hash."""
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        extractor = SemanticExtractor.get_instance()
        result1 = extractor.extract(frame, 1, 1234567890.0)
        result2 = extractor.extract(frame, 1, 1234567890.0)

        assert result1 is not None
        assert result2 is not None
        assert result1.json_str == result2.json_str
        assert result1.semantic_hash == result2.semantic_hash

    def test_different_frames_different_hashes(self):
        """Test that different frames produce different hashes (usually)."""
        frame1 = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        frame2 = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        extractor = SemanticExtractor.get_instance()
        result1 = extractor.extract(frame1, 1, 1234567890.0)
        result2 = extractor.extract(frame2, 2, 1234567890.0)

        # Different GOP IDs should produce different hashes
        assert result1 is not None
        assert result2 is not None
        assert result1.semantic_hash != result2.semantic_hash

    def test_empty_detection(self):
        """Test handling of frames with no detections."""
        # Solid color frame (unlikely to detect objects)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        extractor = SemanticExtractor.get_instance()
        result = extractor.extract(frame, 1, 1234567890.0)

        assert result is not None
        assert result.total_count == 0
        assert result.objects == {}

    def test_invalid_frame_none(self):
        """Test handling of None frame."""
        extractor = SemanticExtractor.get_instance()
        result = extractor.extract(None, 1, 1234567890.0)

        assert result is None

    def test_invalid_frame_empty(self):
        """Test handling of empty array."""
        extractor = SemanticExtractor.get_instance()
        result = extractor.extract(np.array([]), 1, 1234567890.0)

        assert result is None

    def test_invalid_frame_wrong_dimensions(self):
        """Test handling of wrong dimensions."""
        extractor = SemanticExtractor.get_instance()
        # 2D array instead of 3D
        result = extractor.extract(np.zeros((480, 640), dtype=np.uint8), 1, 1234567890.0)

        assert result is None

    def test_json_structure(self):
        """Test that JSON has expected structure."""
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        extractor = SemanticExtractor.get_instance()
        result = extractor.extract(frame, 123, 1234567890.5)

        assert result is not None

        # Parse JSON to verify structure
        import json
        data = json.loads(result.json_str)

        assert "gop_id" in data
        assert data["gop_id"] == 123
        assert "timestamp" in data
        assert "objects" in data
        assert isinstance(data["objects"], dict)
        assert "total_count" in data
        assert isinstance(data["total_count"], int)

    def test_timestamp_format(self):
        """Test that timestamp is in ISO 8601 format."""
        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)

        extractor = SemanticExtractor.get_instance()
        result = extractor.extract(frame, 1, 1234567890.0)

        assert result is not None
        # Should be ISO 8601 format: YYYY-MM-DDTHH:MM:SS with timezone
        assert "T" in result.timestamp
        # Accept both Z and +00:00 timezone formats
        assert result.timestamp.endswith("Z") or result.timestamp.endswith("+00:00")

    def test_thread_safety(self):
        """Test concurrent extraction (basic thread safety check)."""
        import threading

        frame = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
        results = []

        def extract():
            extractor = SemanticExtractor.get_instance()
            result = extractor.extract(frame, 1, 1234567890.0)
            results.append(result)

        threads = [threading.Thread(target=extract) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should succeed
        assert len(results) == 5
        assert all(r is not None for r in results)
        # All should produce same hash (same input)
        hashes = [r.semantic_hash for r in results]
        assert len(set(hashes)) == 1
