"""Tests for ml.snr_eval (tiny run so the full eval isn't needed)."""

from __future__ import annotations

import json
import math

from ml.snr_eval import evaluate, write_curve


def test_tiny_snr_eval_writes_valid_json(tmp_path):
    report = evaluate(snrs_db=[-20, 8], n_per_snr=10, seed=7)

    # Write to a tmp path so the real ml/snr_eval.json isn't touched.
    out = tmp_path / "snr_eval.json"
    out.write_text(json.dumps(report, indent=2) + "\n")
    data = json.loads(out.read_text())

    assert data["data"] == "synthetic"
    assert data["seed"] == 7
    assert data["n_per_snr"] == 10
    assert data["training_snr_range_db"] == [-8, 10]
    assert [r["snr_db"] for r in data["results"]] == [-20, 8]

    for row in data["results"]:
        assert set(row) == {"snr_db", "accuracy", "auc", "recall"}
        for key in ("accuracy", "auc", "recall"):
            val = row[key]
            assert isinstance(val, (int, float))
            assert math.isnan(val) or 0.0 <= val <= 1.0


def test_write_curve_creates_png(tmp_path):
    report = evaluate(snrs_db=[-20, 8], n_per_snr=10, seed=7)
    png = tmp_path / "snr_curve.png"
    write_curve(report, out_path=png)
    assert png.exists() and png.stat().st_size > 0
