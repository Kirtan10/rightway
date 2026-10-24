# Requirements — backend-sim

## Introduction

The backend serves a FastAPI app that simulates vessel traffic in Massachusetts
Bay, issues a 10 nm slow zone when an up-call is detected, computes compliance,
and exposes the API contract from `.kiro/steering/structure.md`. All vessel data
is simulated (`"simulated": true`); confidence comes from `ml.predict.predict`
and is never hard-coded. Ownership note: this spec covers `backend/` except
`backend/brief.py` and `backend/cache/brief.json`, which are unchanged.

## Requirements

### R1 — FastAPI app and CORS
THE SYSTEM SHALL serve a FastAPI app from `backend/app.py`, runnable with
`uvicorn backend.app:app --port 8000` from the repo root, with CORS allowing
`http://localhost:5500` and `http://127.0.0.1:5500`.

### R2 — Nine simulated vessels
THE SYSTEM SHALL simulate 9 vessels in Massachusetts Bay (state in
`backend/sim.py`) with starting speeds (knots): Mystic 9, Atlantic Star 18,
Orion Bay 17, Blue Fin II 11, Nordic Tide 16, Harbor Queen 22, Cape Runner 19,
Sea Ledger 15, Gull Point 8. Most sit along a Boston shipping lane running
roughly east from Boston Harbor.

### R3 — Four hydrophones, H-2 membership
THE SYSTEM SHALL define 4 hydrophones H-1 to H-4. H-2 SHALL be placed so that
exactly Nordic Tide, Harbor Queen, Blue Fin II, and Cape Runner are within
10 nm, and the other 5 vessels are more than 10 nm away. This membership SHALL
hold for every clock time and every detection time given the bounded ship
movement in R14 (verified by a Hypothesis property test over haversine
distance).

### R4 — POST /detections
WHEN `POST /detections {"hydrophone_id","wav"}` is received THE SYSTEM SHALL
call `ml.predict.predict(wav)` for the confidence (default wav
`ml/demo_upcall.wav`; only paths inside `ml/` are allowed), never hard-coding a
score; create a 10 nm zone centered on that hydrophone; mark in-zone vessels
`alerted` using their CURRENT positions at detection time; and return
`{detection_id, hydrophone_id, confidence,
zone{lat,lon,radius_nm:10}, vessels_in_zone[{id,name,speed_before}],
synthetic_demo_clip:true, simulated:true}`.

### R5 — Lazy response after delay
WHEN `SIM_RESPONSE_SECONDS` (default 4) have passed since the detection THE
SYSTEM SHALL move alerted vessels to their response: Nordic Tide 16->10,
Harbor Queen 22->10, Blue Fin II 11->9 (`complying`), Cape Runner 19->17
(`not_complying`). This SHALL be computed lazily on read via an injectable
clock, with no background threads.

### R6 — GET /vessels
`GET /vessels` -> list of `{id,name,type,lat,lon,heading,speed,status,
simulated:true}`, where `lat`/`lon` are the ship's CURRENT position and
`heading` is its current heading (flipped 180 deg while it travels back toward
its seed; see R14).

### R6a — GET /hydrophones
`GET /hydrophones` -> list of `{id,lat,lon,simulated:true}` for the 4
hydrophones already defined in `backend/sim.py` (H-1 to H-4), with their
positions unchanged. H-2's position SHALL match the `/detections` zone center.

### R7 — GET /compliance
`GET /compliance` -> `{compliance_pct, vessels[{id,name,before,after,status}],
simulated:true}`. `compliance_pct = complying / in-zone * 100` (75.0 in the
demo), or `null` before any detection or before the response time has passed.

### R8 — GET /brief
Before a detection, or before the in-zone vessels have responded
(`compliance_pct` is null), `GET /brief` SHALL return `backend/cache/brief.json`
as-is, adding `"source":"cache"` if missing; if the file is missing it SHALL
return `{"brief":"Brief not generated yet.","source":"cache"}`.

WHEN a detection is active AND the vessels have responded, `GET /brief` SHALL
build `(detection, compliance)` from the current sim state in the same shape as
`brief.build_demo_input()` (hydrophone, confidence, confidence_display, zone,
vessels_in_zone, compliance_pct, compliance_display, per-vessel
before/after/status, simulated flags) and call
`brief.generate_brief_result(detection, compliance)`. The result SHALL be cached
in memory keyed by `detection_id` so Bedrock is called at most once per
detection, and `POST /reset` SHALL clear that cache. The response SHALL be
`{"brief","source","detection_id","generated_at"}` where `source` is `"bedrock"`
only if the live call passed validation; otherwise the brief text comes from
`backend/cache/brief.json` with `source` `"cache"`. The route SHALL be a sync
`def` (run in FastAPI's threadpool) so the blocking Bedrock call never blocks the
event loop. The route SHALL NOT import prompt/validation internals of
`backend/brief.py` beyond calling `generate_brief_result`.

### R9 — GET /stats
`GET /stats` -> `{detections, alerts_sent, compliance_pct, simulated:true}`,
counted from sim events only, starting at 0.

### R10 — POST /reset
`POST /reset` SHALL restore the initial state (including each ship's seed
position and the movement clock baseline, so ships resume from their seeds),
clear detections, and zero stats.

### R11 — Static ML assets, read-only
THE SYSTEM SHALL serve `ml/demo_spectrogram.png`, `ml/demo_spectrogram.json`,
`ml/noise_spectrogram.png`, and `ml/demo_upcall.wav` read-only at
`/static/<filename>` (only those 4 files), without copying or modifying any
`ml/` files.

### R12 — predict() failure -> 503
IF `predict()` raises THEN THE SYSTEM SHALL return HTTP 503 with the error
message and SHALL NOT invent a score.

### R13 — One active detection at a time
IF a detection is already active THEN `POST /detections` SHALL return HTTP 409
with detail "A detection is already active. Reset first." and SHALL change
nothing (no model call, no state change). A `POST /reset` clears the active
detection so a new detection is allowed again.

### R14 — Ships move (lazy, accelerated, ping-pong)
THE SYSTEM SHALL move each ship along its heading at its CURRENT speed, computed
lazily from the injectable clock with no background threads. Simulated time
SHALL be accelerated by a configurable `TIME_SCALE` (default 60, so 1 real
second = 1 simulated minute). To keep the demo stable, each ship SHALL
ping-pong back and forth along its heading line within `MAX_OFFSET_NM` (default
1.5) of its seed position, reversing direction at each end. Distance SHALL be
integrated piecewise so a speed change after an alert takes effect from that
moment (a slowed ship visibly covers less distance per simulated minute, while
Cape Runner stays fast). Every ship SHALL always remain within `MAX_OFFSET_NM`
of its seed position.
