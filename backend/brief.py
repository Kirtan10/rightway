"""Generate a harbor-authority brief from a detection + compliance snapshot.

Uses Amazon Bedrock (Converse API) when available, and otherwise falls back to
the hand-written cached brief in backend/cache/brief.json.

Honesty rules (see .kiro/steering/product.md): the brief must state that vessel
data is simulated and the demo clip is synthetic. The Bedrock output is trusted
only when it is exactly 3 sentences, mentions the "right whale up-call", the
"10 nm" slow zone, and that data is "simulated", and uses no arrows ("->"/"\u2192");
otherwise the cached brief is returned.

Public interface:
    generate_brief(detection, compliance) -> str          # contract function
    generate_brief_result(detection, compliance) -> dict   # {"brief","source"}
    build_demo_input() -> (detection, compliance)

Run:
    python -m backend.brief
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from backend.sim import HYDROPHONES

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT / "backend" / "cache" / "brief.json"
DEMO_RESULT_PATH = ROOT / "ml" / "demo_result.json"

DEFAULT_REGION = "us-east-1"
MAX_TOKENS = 300
TEMPERATURE = 0.2

SYSTEM_PROMPT = (
    "You are writing a short internal situation note for harbor authorities. "
    "Do not include any greeting or salutation. Use ONLY the facts in the "
    "JSON provided; never invent, average, total, or recompute any number. "
    "Write exactly three plain-language sentences that read naturally, and "
    "nothing else. "
    "Sentence 1: state that hydrophone H-2 detected a likely "
    '"right whale up-call" (use that exact phrase) with a confidence of '
    "the value given in confidence_display, and that a "
    '"10 nm slow zone" (use that exact phrase) was set around it. '
    "Sentence 2: describe how each vessel responded, naming every vessel and "
    'writing its speed change in the form "16 to 10 knots" (always use the '
    'word "to"; never use an arrow or the characters "->"), and state the '
    "compliance percentage exactly as given. "
    "State the compliance percentage by copying compliance_display exactly, "
    "including the % sign (for example 75%); never write the word percent. "
    "In sentence 2, vary the verbs and don't repeat 'reduced speed' for every "
    "vessel. "
    "Sentence 3: give a recommended action that names the vessel that is not "
    "complying, and end that same sentence with a note that all vessel data "
    "is simulated and the detection clip is a synthetic demo clip (do not put "
    "that note in a separate sentence). "
    "Write the phrases right whale up-call and 10 nm slow zone as normal "
    "words, without quotation marks."
)

# Exact number of sentences accepted from Bedrock before falling back to cache.
REQUIRED_BRIEF_SENTENCES = 3

# Phrases that must appear in accepted Bedrock output (case-insensitive).
REQUIRED_BRIEF_PHRASES = ("right whale up-call", "10 nm", "simulated")

# Substrings that must NOT appear in accepted Bedrock output: arrows and the
# double-quote character (phrases must be written as normal words).
FORBIDDEN_BRIEF_SUBSTRINGS = ("->", "\u2192", '"')


def _get_client():
    """Build a bedrock-runtime client.

    boto3 is imported lazily so a missing dependency is a handled fallback and
    so tests can monkeypatch this helper. Raises RuntimeError if boto3 is
    missing or BEDROCK_MODEL_ID is unset; callers treat that as a fallback
    trigger.
    """
    model_id = os.environ.get("BEDROCK_MODEL_ID")
    if not model_id:
        raise RuntimeError("BEDROCK_MODEL_ID is not set")
    try:
        import boto3
    except ImportError as exc:  # boto3 not installed -> fall back to cache
        raise RuntimeError("boto3 is not installed") from exc
    region = os.environ.get("AWS_REGION", DEFAULT_REGION)
    return boto3.client("bedrock-runtime", region_name=region)


def _user_message(detection: dict[str, Any], compliance: dict[str, Any]) -> str:
    """Serialize the inputs as JSON for the user turn."""
    return json.dumps({"detection": detection, "compliance": compliance}, indent=2)


def _call_bedrock(detection: dict[str, Any], compliance: dict[str, Any]) -> str:
    """Call Bedrock Converse and return the model's text output."""
    client = _get_client()
    model_id = os.environ["BEDROCK_MODEL_ID"]
    response = client.converse(
        modelId=model_id,
        system=[{"text": SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": _user_message(detection, compliance)}]}],
        inferenceConfig={"maxTokens": MAX_TOKENS, "temperature": TEMPERATURE},
    )
    return response["output"]["message"]["content"][0]["text"].strip()


def _read_cache() -> str:
    """Return the cached brief text from backend/cache/brief.json."""
    data = json.loads(CACHE_PATH.read_text())
    return data["brief"]


def _count_sentences(text: str) -> int:
    """Count sentences by terminal punctuation (., !, ?).

    Consecutive terminators (e.g. "...") count once, and a decimal point
    between digits (e.g. "9.5") is not treated as a sentence boundary.
    """
    # Drop decimal points that sit between digits so they don't end a sentence.
    cleaned = re.sub(r"(?<=\d)\.(?=\d)", "", text)
    # Collapse runs of terminal punctuation to a single marker.
    return len(re.findall(r"[.!?]+", cleaned))


# A digit glued directly to an ASCII letter (e.g. "at75" or "75knots").
_DIGIT_LETTER_RE = re.compile(r"[A-Za-z]\d|\d[A-Za-z]")


def _compliance_pct_text(compliance: dict[str, Any]) -> str:
    """Render the compliance percentage exactly as it must appear (e.g. 75%)."""
    pct = compliance["compliance_pct"]
    return f"{pct:g}%"


def _validation_failure(text: str, compliance: dict[str, Any]) -> str | None:
    """Return a reason string if `text` fails any check, else None.

    Accepted output must: be non-empty; have exactly REQUIRED_BRIEF_SENTENCES
    sentences; contain every phrase in REQUIRED_BRIEF_PHRASES; contain the
    compliance percentage written exactly as f"{pct:g}%"; contain no substring
    in FORBIDDEN_BRIEF_SUBSTRINGS (arrows/quotes); and contain no digit glued
    directly to a letter (e.g. "at75").
    """
    if not text:
        return "empty output"

    n = _count_sentences(text)
    if n != REQUIRED_BRIEF_SENTENCES:
        return f"expected {REQUIRED_BRIEF_SENTENCES} sentences, found {n}"

    lowered = text.lower()
    for phrase in REQUIRED_BRIEF_PHRASES:
        if phrase not in lowered:
            return f"missing required phrase {phrase!r}"

    pct_text = _compliance_pct_text(compliance)
    if pct_text not in text:
        return f"missing compliance percentage {pct_text!r}"

    for bad in FORBIDDEN_BRIEF_SUBSTRINGS:
        if bad in text:
            return f"contains forbidden substring {bad!r}"

    m = _DIGIT_LETTER_RE.search(text)
    if m:
        return f"digit glued to a letter: {m.group(0)!r}"

    return None


def generate_brief_result(
    detection: dict[str, Any], compliance: dict[str, Any]
) -> dict[str, str]:
    """Return {"brief", "source"} using Bedrock when possible, else the cache.

    Bedrock output is accepted only when it passes every check in
    _validation_failure (exactly 3 sentences; contains "right whale up-call",
    "10 nm", "simulated", and the compliance percentage as "{pct:g}%"; has no
    "->"/"\u2192" arrows or double-quotes; and no digit glued to a letter). Any
    Bedrock failure, or any failed check, logs a warning naming the check and
    falls back to the cached brief.
    """
    try:
        text = _call_bedrock(detection, compliance)
        reason = _validation_failure(text, compliance)
        if reason is None:
            return {"brief": text, "source": "bedrock"}
        logger.warning("Rejected Bedrock output (%s); falling back to cache.", reason)
    except Exception:
        logger.warning("Bedrock call failed; falling back to cache.", exc_info=True)
    return {"brief": _read_cache(), "source": "cache"}


def generate_brief(detection: dict[str, Any], compliance: dict[str, Any]) -> str:
    """Contract function: return only the brief text."""
    return generate_brief_result(detection, compliance)["brief"]


def _demo_result() -> dict[str, Any]:
    """Read the cached demo result (confidence never hard-coded).

    Raises a clear error if ml/demo_result.json is missing, naming the path and
    telling the user how to create it.
    """
    if not DEMO_RESULT_PATH.exists():
        raise FileNotFoundError(
            f"Demo result not found: {DEMO_RESULT_PATH}. "
            "Run `python -m ml.cache_demo` to create it."
        )
    return json.loads(DEMO_RESULT_PATH.read_text())


def build_demo_input() -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (detection, compliance) matching the structure.md Demo canon."""
    demo = _demo_result()
    confidence = float(demo["confidence"])
    # 2-decimal display string from ml/demo_result.json, never a percentage.
    confidence_display = f"{float(demo['confidence_display']):.2f}"
    # Zone center is the H-2 hydrophone from the sim (never hard-coded here).
    h2_lat, h2_lon = HYDROPHONES["H-2"]
    detection = {
        "detection_id": "DET-DEMO-1",
        "hydrophone_id": "H-2",
        "confidence": confidence,
        "confidence_display": confidence_display,
        "zone": {"lat": h2_lat, "lon": h2_lon, "radius_nm": 10},
        "vessels_in_zone": [
            {"id": "V-5", "name": "Nordic Tide", "speed_before": 16},
            {"id": "V-6", "name": "Harbor Queen", "speed_before": 22},
            {"id": "V-4", "name": "Blue Fin II", "speed_before": 11},
            {"id": "V-7", "name": "Cape Runner", "speed_before": 19},
        ],
        "synthetic_demo_clip": True,
        "simulated": True,
    }
    compliance_pct = 75
    compliance = {
        "compliance_pct": compliance_pct,
        "compliance_display": f"{compliance_pct:g}%",
        "vessels": [
            {"id": "V-5", "name": "Nordic Tide", "before": 16, "after": 10, "status": "complying"},
            {"id": "V-6", "name": "Harbor Queen", "before": 22, "after": 10, "status": "complying"},
            {"id": "V-4", "name": "Blue Fin II", "before": 11, "after": 9, "status": "complying"},
            {
                "id": "V-7",
                "name": "Cape Runner",
                "before": 19,
                "after": 17,
                "status": "not_complying",
            },
        ],
    }
    return detection, compliance


def main() -> None:
    detection, compliance = build_demo_input()
    result = generate_brief_result(detection, compliance)
    # Only persist fresh Bedrock output; never overwrite the cache with itself.
    if result["source"] == "bedrock":
        CACHE_PATH.write_text(
            json.dumps({"brief": result["brief"], "source": "bedrock"}, indent=2) + "\n"
        )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
