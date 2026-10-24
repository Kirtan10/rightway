"""FastAPI app for RightWay (app-owner side of the backend).

Run from the repo root:
    uvicorn backend.app:app --port 8000

All vessel data is simulated. Confidence comes from ml.predict.predict and is
never hard-coded. The /brief route reads backend/cache/brief.json directly and
never imports backend/brief.py.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import brief as brief_module
from .sim import ML_DIR, ROOT, Simulation, resolve_wav

app = FastAPI(title="RightWay backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5500", "http://127.0.0.1:5500"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Single simulation instance. Tests may replace app.state.sim with one that has
# an injected clock.
app.state.sim = Simulation()

# In-memory per-detection brief cache (keyed by detection_id) so Bedrock is
# called at most once per detection. Cleared on /reset.
app.state.brief_cache = {}

# Allow-list of ML assets served read-only at /static/<filename>.
STATIC_FILES = {
    "demo_spectrogram.png",
    "demo_spectrogram.json",
    "noise_spectrogram.png",
    "demo_upcall.wav",
}


def _sim() -> Simulation:
    return app.state.sim


def _brief_cache() -> dict[str, dict[str, Any]]:
    if not hasattr(app.state, "brief_cache"):
        app.state.brief_cache = {}
    return app.state.brief_cache


class DetectionRequest(BaseModel):
    hydrophone_id: str
    wav: str | None = None


@app.get("/vessels")
def get_vessels() -> list[dict[str, Any]]:
    return _sim().vessels()


@app.get("/hydrophones")
def get_hydrophones() -> list[dict[str, Any]]:
    return _sim().hydrophones()


@app.post("/detections")
def post_detection(req: DetectionRequest) -> dict[str, Any]:
    # Only one active detection at a time; require a reset before the next.
    if _sim().has_active_detection():
        raise HTTPException(
            status_code=409, detail="A detection is already active. Reset first."
        )

    # Resolve + validate the wav path (only inside ml/).
    try:
        wav_path = resolve_wav(req.wav)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not wav_path.exists():
        raise HTTPException(status_code=400, detail=f"wav not found: {req.wav}")

    # Confidence from the model only; a failure is a 503, never a made-up score.
    from ml.predict import predict

    try:
        confidence = predict(str(wav_path))
    except Exception as exc:
        # Surface any model failure as 503; never invent a score.
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        return _sim().create_detection(req.hydrophone_id, confidence)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/compliance")
def get_compliance() -> dict[str, Any]:
    return _sim().compliance()


@app.get("/stats")
def get_stats() -> dict[str, Any]:
    return _sim().stats()


@app.post("/reset")
def post_reset() -> dict[str, Any]:
    _sim().reset()
    _brief_cache().clear()
    return {"ok": True}


def _cached_file_brief() -> dict[str, Any]:
    """Return backend/cache/brief.json (source 'cache'), or a placeholder."""
    path = _sim().brief_default_path()
    if not path.exists():
        return {"brief": "Brief not generated yet.", "source": "cache"}
    data = json.loads(path.read_text())
    data.setdefault("source", "cache")
    return data


# Sync def: FastAPI runs it in a threadpool, so the blocking Bedrock call never
# blocks the event loop.
@app.get("/brief")
def get_brief() -> dict[str, Any]:
    inputs = _sim().brief_inputs()

    # Before a detection, or before the vessels have responded, serve the file.
    if inputs is None:
        return _cached_file_brief()

    detection, compliance = inputs
    detection_id = detection["detection_id"]
    cache = _brief_cache()

    # Build (and generate) at most once per detection; reuse the cached result.
    if detection_id not in cache:
        result = brief_module.generate_brief_result(detection, compliance)
        if result["source"] == "bedrock":
            payload = {"brief": result["brief"], "source": "bedrock"}
        else:
            # Live call failed validation / was unavailable: use the file.
            payload = {"brief": _cached_file_brief()["brief"], "source": "cache"}
        payload["detection_id"] = detection_id
        payload["generated_at"] = datetime.now(UTC).isoformat()
        cache[detection_id] = payload

    return cache[detection_id]


@app.get("/static/{filename}")
def get_static(filename: str) -> FileResponse:
    if filename not in STATIC_FILES:
        raise HTTPException(status_code=404, detail="not found")
    target: Path = ML_DIR / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(target)


# Serve the frontend for single-server hosting. Mounted at "/" AFTER every API
# route so the specific routes above take precedence; html=True serves
# index.html at "/".
app.mount("/", StaticFiles(directory=ROOT / "frontend", html=True), name="frontend")
