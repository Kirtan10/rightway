"""Cache the demo prediction result.

Runs predict() on ml/demo_upcall.wav and writes ml/demo_result.json so the rest
of the system can read a canonical demo confidence without re-running the model.

The demo clip is a SYNTHETIC demo clip (see .kiro/steering/product.md); the
confidence always comes from ml/predict.py and is never hard-coded.

Run:
    python -m ml.cache_demo
"""

from __future__ import annotations

import json
from pathlib import Path

from .predict import predict

ROOT = Path(__file__).resolve().parent
DEMO_WAV = ROOT / "demo_upcall.wav"
DEMO_RESULT_PATH = ROOT / "demo_result.json"
# Relative label stored in the JSON (repo-root relative, POSIX style).
CLIP_LABEL = "ml/demo_upcall.wav"


def build_demo_result(wav_path: Path = DEMO_WAV) -> dict:
    """Run predict() on the demo clip and return the result dict."""
    confidence = predict(str(wav_path))
    return {
        "confidence": round(confidence, 4),
        "confidence_display": f"{confidence:.2f}",
        "clip": CLIP_LABEL,
        "synthetic_demo_clip": True,
    }


def write_demo_result(out_path: Path = DEMO_RESULT_PATH, wav_path: Path = DEMO_WAV) -> dict:
    """Build the demo result and write it to `out_path` as JSON."""
    result = build_demo_result(wav_path)
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    result = write_demo_result()
    print(f"Wrote {DEMO_RESULT_PATH}")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
