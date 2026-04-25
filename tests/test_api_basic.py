import importlib
import json
import sys
import types

import pytest


pytestmark = pytest.mark.api


@pytest.fixture
def server_module(monkeypatch, temp_video_store):
    from services import detection_service

    monkeypatch.setattr(detection_service, "start_detection_loop", lambda *args, **kwargs: None)

    class FakeAsyncIOScheduler:
        def add_job(self, *args, **kwargs):
            return None

        def start(self):
            return None

        def shutdown(self):
            return None

    scheduler_module = types.ModuleType("apscheduler.schedulers.asyncio")
    scheduler_module.AsyncIOScheduler = FakeAsyncIOScheduler
    monkeypatch.setitem(sys.modules, "apscheduler", types.ModuleType("apscheduler"))
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers", types.ModuleType("apscheduler.schedulers"))
    monkeypatch.setitem(sys.modules, "apscheduler.schedulers.asyncio", scheduler_module)

    module = importlib.import_module("demo2.server")
    monkeypatch.setattr(module, "list_videos", temp_video_store.list_videos)
    monkeypatch.setattr(module, "list_verify_history", temp_video_store.list_verify_history)
    return module


def test_video_list_endpoint_returns_current_store(server_module, temp_video_store):
    temp_video_store.insert_video(
        video_id="video-1",
        device_id="cam-1",
        filename="sample.mp4",
        file_size=123,
        gop_count=0,
        merkle_root="a" * 64,
        tx_id="tx-1",
        block_number=1,
        created_at=1000.0,
    )

    response = server_module.api_video_list()

    assert response.status_code == 200
    body = json.loads(response.body.decode("utf-8"))
    assert body["videos"][0]["id"] == "video-1"


def test_verification_stats_endpoint_uses_verify_history(server_module, temp_video_store):
    temp_video_store.insert_verify_record(
        original_video_id="video-1",
        uploaded_filename="candidate.mp4",
        overall_status="INTACT",
        overall_risk=0.0,
        gop_results=[],
    )
    temp_video_store.insert_verify_record(
        original_video_id="video-1",
        uploaded_filename="tampered.mp4",
        overall_status="TAMPERED",
        overall_risk=0.9,
        gop_results=[],
    )

    body = server_module.api_verify_stats()

    assert body["total_verifications"] == 2
    assert body["status_counts"]["INTACT"] == 1
    assert body["status_counts"]["TAMPERED"] == 1
    assert body["integrity_rate"] == 0.5
