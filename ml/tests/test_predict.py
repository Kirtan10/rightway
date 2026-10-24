"""Tests for ml.predict.predict()."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from ml import predict as predict_mod
from ml.predict import predict

ROOT = Path(__file__).resolve().parents[1]


def _any_wav() -> Path:
    """Find a real clip to test against; synthesize one if none exist."""
    syn = ROOT / "data" / "synthetic"
    clips = sorted(syn.glob("*.wav")) if syn.exists() else []
    if clips:
        return clips[0]
    tmp = ROOT / "data" / "_pytest_tmp.wav"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    sf.write(tmp, (np.random.randn(4000) * 0.05).astype("float32"), 2000, subtype="PCM_16")
    return tmp


def test_predict_returns_float_in_unit_interval():
    conf = predict(str(_any_wav()))
    assert isinstance(conf, float)
    assert 0.0 <= conf <= 1.0


def test_missing_file_raises_clear_error():
    missing = str(ROOT / "data" / "does_not_exist_zzz.wav")
    with pytest.raises(FileNotFoundError) as exc:
        predict(missing)
    assert "not found" in str(exc.value).lower()


def test_missing_model_raises_runtime_error_naming_path(monkeypatch):
    """When model weights are absent, predict() must raise a clear RuntimeError
    that names the model path, with no silent stand-in fallback."""
    bogus = ROOT / "model_does_not_exist_zzz.pt"
    monkeypatch.setattr(predict_mod, "MODEL_PATH", bogus)
    # Reset the lazy-load cache so _load_model re-evaluates MODEL_PATH.
    monkeypatch.setattr(predict_mod, "_MODEL", None)
    monkeypatch.setattr(predict_mod, "_DEVICE", None)

    with pytest.raises(RuntimeError) as exc:
        predict(str(_any_wav()))
    assert str(bogus) in str(exc.value)
