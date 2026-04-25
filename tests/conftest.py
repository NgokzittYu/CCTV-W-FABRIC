import hashlib
import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest


@pytest.fixture
def synthetic_frame():
    rng = np.random.RandomState(42)
    return rng.randint(0, 255, size=(32, 48, 3), dtype=np.uint8)


@pytest.fixture
def fixed_vifs():
    return {
        "zero": "0" * 64,
        "one_bit": ("0" * 63) + "1",
        "half": "f" * 32 + "0" * 32,
        "all": "f" * 64,
    }


@pytest.fixture
def hash_hex():
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    return _hash


@pytest.fixture
def temp_video_store(monkeypatch, tmp_path):
    from services import video_store

    if hasattr(video_store._local, "conn") and video_store._local.conn is not None:
        video_store._local.conn.close()
        video_store._local.conn = None

    db_path = tmp_path / "video_store.db"
    monkeypatch.setattr(video_store, "DB_PATH", db_path)
    video_store.init_db()

    yield video_store

    if hasattr(video_store._local, "conn") and video_store._local.conn is not None:
        video_store._local.conn.close()
        video_store._local.conn = None


def assert_jsonable(value):
    json.dumps(value, ensure_ascii=False)
