import numpy as np
import pytest

from services import vif
from services.vif import VIFConfig, compute_vif


pytestmark = pytest.mark.unit


def _constant_feature(value: float) -> np.ndarray:
    return np.full(576, value, dtype=np.float64)


def test_vif_output_is_256_bit_hex(monkeypatch, synthetic_frame):
    monkeypatch.setattr(vif, "extract_phash_feature", lambda frame: _constant_feature(1.0))

    result = compute_vif([synthetic_frame], VIFConfig(mode="fusion"))

    assert result is not None
    assert len(result) == 64
    int(result, 16)


def test_vif_is_deterministic_for_same_features(monkeypatch, synthetic_frame):
    monkeypatch.setattr(vif, "extract_phash_feature", lambda frame: _constant_feature(0.25))

    first = compute_vif([synthetic_frame], VIFConfig(mode="fusion"))
    second = compute_vif([synthetic_frame], VIFConfig(mode="fusion"))

    assert first == second


def test_vif_changes_when_features_change(monkeypatch, synthetic_frame):
    calls = iter([_constant_feature(0.25), _constant_feature(-0.25)])
    monkeypatch.setattr(vif, "extract_phash_feature", lambda frame: next(calls))

    first = compute_vif([synthetic_frame], VIFConfig(mode="fusion"))
    second = compute_vif([synthetic_frame], VIFConfig(mode="fusion"))

    assert first != second


def test_vif_returns_none_when_off_or_empty(synthetic_frame):
    assert compute_vif([synthetic_frame], VIFConfig(mode="off")) is None
    assert compute_vif([], VIFConfig(mode="fusion")) is None
