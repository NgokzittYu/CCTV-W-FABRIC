import pytest


pytestmark = pytest.mark.unit


def test_video_store_roundtrip(temp_video_store):
    store = temp_video_store

    video = store.insert_video(
        video_id="video-1",
        device_id="cam-1",
        filename="sample.mp4",
        file_size=123,
        gop_count=2,
        merkle_root="a" * 64,
        tx_id="tx-1",
        block_number=7,
        created_at=1000.0,
    )
    store.insert_video_gops(
        "video-1",
        [
            {
                "video_id": "video-1",
                "gop_index": 0,
                "sha256": "b" * 64,
                "vif": "c" * 64,
                "start_time": 10.0,
                "end_time": 12.0,
                "frame_count": 30,
                "byte_size": 1000,
            },
            {
                "video_id": "video-1",
                "gop_index": 1,
                "sha256": "d" * 64,
                "vif": "e" * 64,
                "start_time": 12.0,
                "end_time": 14.0,
                "frame_count": 30,
                "byte_size": 900,
            },
        ],
    )

    assert video["id"] == "video-1"
    assert store.get_video("video-1")["filename"] == "sample.mp4"
    assert [g["gop_index"] for g in store.get_video_gops("video-1")] == [0, 1]
    assert len(store.get_device_gops_by_time("cam-1", 11.0, 13.0)) == 2


def test_verify_history_roundtrip(temp_video_store):
    store = temp_video_store

    record = store.insert_verify_record(
        original_video_id="video-1",
        uploaded_filename="candidate.mp4",
        overall_status="RE_ENCODED",
        overall_risk=0.12,
        gop_results=[{"gop_index": 0, "status": "RE_ENCODED"}],
        verify_mode="original_video",
        matched_gop_count=1,
    )
    history = store.list_verify_history()

    assert history[0]["id"] == record["id"]
    assert history[0]["gop_results"] == [{"gop_index": 0, "status": "RE_ENCODED"}]
    assert history[0]["matched_gop_count"] == 1
