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
        "Hydrophone H-2 detected a likely right whale up-call at 1.00 confidence, "
        "and a 10 nm slow zone was set around it. "
        "Nordic Tide slowed 16 to 10 knots, Harbor Queen eased 22 to 10 knots, "
        "Blue Fin II dropped 11 to 9 knots, and Cape Runner held 19 to 17 knots, "
        "for 75% compliance. "
        "Authorities should contact Cape Runner to confirm compliance; all vessel "
        "data is simulated and the detection clip is a synthetic demo clip."
    )
    monkeypatch.setattr(brief, "_get_client", lambda: _FakeClient(fake))
    monkeypatch.setenv("BEDROCK_MODEL_ID", "fake-model")
    detection, compliance = brief.build_demo_input()
    result = brief.generate_brief_result(detection, compliance)

    assert result["source"] == "bedrock"
    assert result["brief"] == fake


def test_output_with_arrow_falls_back_to_cache(monkeypatch):
    # Uses "->" arrows instead of the required "16 to 10 knots" wording.
    fake = (
        "Hydrophone H-2 detected a likely right whale up-call at 1.00 confidence, "
        "and a 10 nm slow zone was set around it. "
        "Nordic Tide 16 -> 10 knots, Harbor Queen 22 -> 10 knots, "
        "Blue Fin II 11 -> 9 knots, and Cape Runner 19 -> 17 knots, for 75% compliance. "
        "Authorities should contact Cape Runner; all vessel data is simulated "
        "and the detection clip is a synthetic demo clip."
    )
    monkeypatch.setattr(brief, "_get_client", lambda: _FakeClient(fake))
    monkeypatch.setenv("BEDROCK_MODEL_ID", "fake-model")
    detection, compliance = brief.build_demo_input()
    result = brief.generate_brief_result(detection, compliance)

    assert result["source"] == "cache"
    assert result["brief"] == brief._read_cache()


def test_output_with_digit_glued_to_letter_falls_back_to_cache(monkeypatch):
    # "at75%" glues a digit to a letter, which must be rejected.
    fake = (
        "Hydrophone H-2 detected a likely right whale up-call at 1.00 confidence, "
        "and a 10 nm slow zone was set around it. "
        "Nordic Tide slowed 16 to 10 knots, Harbor Queen eased 22 to 10 knots, "
        "Blue Fin II dropped 11 to 9 knots, and Cape Runner held 19 to 17 knots, "
        "complying at75%. "
        "Authorities should contact Cape Runner; all vessel data is simulated "
        "and the detection clip is a synthetic demo clip."
    )
    monkeypatch.setattr(brief, "_get_client", lambda: _FakeClient(fake))
    monkeypatch.setenv("BEDROCK_MODEL_ID", "fake-model")
    detection, compliance = brief.build_demo_input()
    result = brief.generate_brief_result(detection, compliance)

    assert result["source"] == "cache"
    assert result["brief"] == brief._read_cache()


def test_output_missing_compliance_pct_falls_back_to_cache(monkeypatch):
    # Omits the exact "75%" compliance figure, which must be rejected.
    fake = (
        "Hydrophone H-2 detected a likely right whale up-call at 1.00 confidence, "
        "and a 10 nm slow zone was set around it. "
        "Nordic Tide slowed 16 to 10 knots, Harbor Queen eased 22 to 10 knots, "
        "Blue Fin II dropped 11 to 9 knots, and Cape Runner held 19 to 17 knots, "
        "with most vessels complying. "
        "Authorities should contact Cape Runner; all vessel data is simulated "
        "and the detection clip is a synthetic demo clip."
    )
    monkeypatch.setattr(brief, "_get_client", lambda: _FakeClient(fake))
    monkeypatch.setenv("BEDROCK_MODEL_ID", "fake-model")
    detection, compliance = brief.build_demo_input()
    result = brief.generate_brief_result(detection, compliance)

    assert result["source"] == "cache"
    assert result["brief"] == brief._read_cache()


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
