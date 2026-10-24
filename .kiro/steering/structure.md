# Structure

## Ownership

- `ml/`, `backend/brief.py`, and `backend/cache/brief.json` belong to the ML owner.
- The rest of `backend/` and all of `frontend/` belong to the app owner.
- Shared root files (`ruff.toml`, `requirements.txt`, `README.md`, `.gitignore`)
  need a heads-up to the other owner before changing.
- Never edit the other owner's files.

## API contract

- `predict(wav_path: str) -> float` in `ml/predict.py` (up-call confidence 0–1;
  raises `RuntimeError` if `ml/model.pt` is missing or fails to load).
- `GET /vessels` -> list of `{id,name,type,lat,lon,heading,speed,status}`,
  status in `normal|alerted|complying|not_complying`.
- `POST /detections {"hydrophone_id","wav"}` -> `{detection_id, hydrophone_id,
  confidence, zone{lat,lon,radius_nm}, vessels_in_zone[{id,name,speed_before}],
  synthetic_demo_clip:true, simulated:true}`.
- `GET /compliance` -> `{compliance_pct, vessels[{id,name,before,after,status}]}`.
- `GET /brief` -> `{"brief": "...", "source": "bedrock"|"cache"}`, read from
  `backend/cache/brief.json` and returned as-is.
- `GET /stats` -> `{detections, alerts_sent, compliance_pct, simulated:true}`,
  from sim events only.
- `POST /reset`.

## Demo canon

- 9 vessels, hydrophones H-1 to H-4.
- Detection at H-2, confidence = value in `ml/demo_result.json` (currently 1.00),
  never hard-coded.
- 10 nm zone, 4 vessels in zone:
  - Nordic Tide 16 -> 10
  - Harbor Queen 22 -> 10
  - Blue Fin II 11 -> 9
  - Cape Runner 19 -> 17 (not_complying)
- Compliance 75%.

## Workflow

- Use spec mode for features; execute from `tasks.md`.
- Commit small and often.
- Run `ruff check . && pytest -q` before each commit.
