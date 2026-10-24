"""FastAPI app for RightWay (app-owner side of the backend).

Run from the repo root:
    uvicorn backend.app:app --port 8000

All vessel data is simulated. Confidence comes from ml.predict.predict and is
never hard-coded. The /brief route reads backend/cache/brief.json directly and
never imports backend/brief.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .sim import ML_DIR, Simulation, resolve_wav

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

# Allow-list of ML assets served read-only at /static/<filename>.
STATIC_FILES = {
    "demo_spectrogram.png",
    "demo_spectrogram.json",
    "noise_spectrogram.png",
    "demo_upcall.wav",
}


def _sim() -> Simulation:
    return app.state.sim


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
    return {"ok": True}


@app.get("/brief")
def get_brief() -> dict[str, Any]:
    path = _sim().brief_default_path()
    if not path.exists():
        return {"brief": "Brief not generated yet.", "source": "cache"}
    data = json.loads(path.read_text())
    data.setdefault("source", "cache")
    return data


@app.get("/static/{filename}")
def get_static(filename: str) -> FileResponse:
    if filename not in STATIC_FILES:
        raise HTTPException(status_code=404, detail="not found")
    target: Path = ML_DIR / filename
    if not target.exists():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(target)
