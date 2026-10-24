"""Tests for ml.cache_demo."""

from __future__ import annotations

import json
import re
from pathlib import Path

from ml.cache_demo import DEMO_WAV, write_demo_result
from ml.predict import predict


def test_write_demo_result_writes_valid_json_with_expected_keys(tmp_path):
    out = tmp_path / "demo_result.json"
    result = write_demo_result(out_path=out)

    # File was written and is valid JSON.
    assert out.exists()
    data = json.loads(out.read_text())
    assert data == result

    # Exactly the expected keys are present.
    assert set(data) == {"confidence", "confidence_display", "clip", "synthetic_demo_clip"}
    assert data["clip"] == "ml/demo_upcall.wav"
    assert data["synthetic_demo_clip"] is True


def test_confidence_matches_predict_on_same_file(tmp_path):
    out = tmp_path / "demo_result.json"
    data = write_demo_result(out_path=out)

    expected = round(predict(str(DEMO_WAV)), 4)
    assert data["confidence"] == expected


def test_confidence_display_is_two_decimal_string_not_percentage(tmp_path):
    out = tmp_path / "demo_result.json"
    data = write_demo_result(out_path=out)

    disp = data["confidence_display"]
    assert isinstance(disp, str)
    # Two-decimal fixed-point string, e.g. "1.00" — not a percentage.
    assert re.fullmatch(r"\d+\.\d{2}", disp)
    assert "%" not in disp
    assert disp == f"{data['confidence']:.2f}"


def test_real_demo_result_file_is_not_overwritten_by_tests(tmp_path):
    # Sanity: the test writes only to tmp_path, never the real ml/ file.
    out = tmp_path / "demo_result.json"
    write_demo_result(out_path=out)
    assert out.parent == tmp_path
    assert Path(out).resolve() != (DEMO_WAV.parent / "demo_result.json").resolve()
