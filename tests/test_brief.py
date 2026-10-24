"""Tests for backend.brief."""

from __future__ import annotations

import json
from pathlib import Path

from backend import brief

ROOT = Path(__file__).resolve().parents[1]


class _FakeClient:
    """Minimal stand-in for a bedrock-runtime client."""

    def __init__(self, text: str):
        self._text = text

    def converse(self, **_kwargs):
        return {"output": {"message": {"content": [{"text": self._text}]}}}


def test_bedrock_raises_falls_back_to_cache(monkeypatch):
    def boom():
        raise RuntimeError("bedrock unavailable")

    monkeypatch.setattr(brief, "_get_client", boom)
    detection, compliance = brief.build_demo_input()
    result = brief.generate_brief_result(detection, compliance)

    assert result["source"] == "cache"
    assert result["brief"] == brief._read_cache()


def test_output_missing_simulated_falls_back_to_cache(monkeypatch):
    # Valid-looking output, but without the required word "simulated".
    monkeypatch.setattr(
        brief, "_get_client", lambda: _FakeClient("A whale was detected and ships slowed.")
    )
    monkeypatch.setenv("BEDROCK_MODEL_ID", "fake-model")
    detection, compliance = brief.build_demo_input()
    result = brief.generate_brief_result(detection, compliance)

    assert result["source"] == "cache"
    assert result["brief"] == brief._read_cache()


def test_valid_output_uses_bedrock(monkeypatch):
    fake = (
        "Hydrophone H-2 detected a whale up-call. Ships slowed and compliance was 75%. "
        "Recommend contacting Cape Runner; all vessel data is simulated."
    )
    monkeypatch.setattr(brief, "_get_client", lambda: _FakeClient(fake))
    monkeypatch.setenv("BEDROCK_MODEL_ID", "fake-model")
    detection, compliance = brief.build_demo_input()
    result = brief.generate_brief_result(detection, compliance)

    assert result["source"] == "bedrock"
    assert result["brief"] == fake


def test_cached_brief_mentions_simulated_and_synthetic():
    text = brief._read_cache().lower()
    assert "simulated" in text
    assert "synthetic" in text


def test_build_demo_input_confidence_matches_demo_result():
    detection, _compliance = brief.build_demo_input()
    # The confidence must come from the ML demo result, not a hard-coded value.
    if brief.DEMO_RESULT_PATH.exists():
        expected = float(json.loads(brief.DEMO_RESULT_PATH.read_text())["confidence"])
    else:
        expected = float(json.loads(brief.DEMO_SPECTROGRAM_PATH.read_text())["confidence"])
    assert detection["confidence"] == expected
