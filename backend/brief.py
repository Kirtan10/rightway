"""Generate a harbor-authority brief from a detection + compliance snapshot.

Uses Amazon Bedrock (Converse API) when available, and otherwise falls back to
the hand-written cached brief in backend/cache/brief.json.

Honesty rules (see .kiro/steering/product.md): the brief must state that vessel
data is simulated and the demo clip is synthetic. The Bedrock output is only
trusted when it is non-empty and contains the word "simulated"; otherwise the
cache is returned.

Public interface:
    generate_brief(detection, compliance) -> str          # contract function
    generate_brief_result(detection, compliance) -> dict   # {"brief","source"}
    build_demo_input() -> (detection, compliance)

Run:
    python -m backend.brief
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CACHE_PATH = ROOT / "backend" / "cache" / "brief.json"
DEMO_RESULT_PATH = ROOT / "ml" / "demo_result.json"

DEFAULT_REGION = "us-east-1"
MAX_TOKENS = 300
TEMPERATURE = 0.2

SYSTEM_PROMPT = (
    "You are a harbor authority writing a short public notice. Use ONLY the "
    "JSON provided; do not invent any facts. Write exactly 3 plain-language "
    "sentences: (1) what was detected, naming the hydrophone and the "
    "confidence; (2) how ships responded, using the before/after speeds and "
    "the compliance percentage; (3) a recommended action that names any "
    "vessel that is not complying. You must state that all vessel data is "
    "simulated and that the detection clip is a synthetic demo clip."
)


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


def generate_brief_result(
    detection: dict[str, Any], compliance: dict[str, Any]
) -> dict[str, str]:
    """Return {"brief", "source"} using Bedrock when possible, else the cache.

    The Bedrock output is only accepted when it is non-empty and contains the
    word "simulated"; any failure or a failed check falls back to the cache.
    """
    try:
        text = _call_bedrock(detection, compliance)
        if text and "simulated" in text.lower():
            return {"brief": text, "source": "bedrock"}
    except Exception:  # noqa: BLE001 - any Bedrock/boto3/env failure falls back to cache
        pass
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
    detection = {
        "detection_id": "DET-DEMO-1",
        "hydrophone_id": "H-2",
        "confidence": confidence,
        "confidence_display": confidence_display,
        "zone": {"lat": 42.35, "lon": -70.95, "radius_nm": 10},
        "vessels_in_zone": [
            {"id": "V-1", "name": "Nordic Tide", "speed_before": 16},
            {"id": "V-2", "name": "Harbor Queen", "speed_before": 22},
            {"id": "V-3", "name": "Blue Fin II", "speed_before": 11},
            {"id": "V-4", "name": "Cape Runner", "speed_before": 19},
        ],
        "synthetic_demo_clip": True,
        "simulated": True,
    }
    compliance = {
        "compliance_pct": 75,
        "vessels": [
            {"id": "V-1", "name": "Nordic Tide", "before": 16, "after": 10, "status": "complying"},
            {"id": "V-2", "name": "Harbor Queen", "before": 22, "after": 10, "status": "complying"},
            {"id": "V-3", "name": "Blue Fin II", "before": 11, "after": 9, "status": "complying"},
            {
                "id": "V-4",
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
