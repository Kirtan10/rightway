# Tasks — backend-sim

- [ ] 1. Implement `backend/sim.py`: vessel + hydrophone seed data, haversine,
      `Simulation` with injectable clock, detection/zone logic, lazy response
      transition, compliance, stats, and reset.
      _R2, R3, R4, R5, R7, R9, R10_

- [ ] 2. Implement `backend/app.py`: FastAPI app, CORS for the two localhost
      origins, `/vessels`, `/detections`, `/compliance`, `/brief`, `/stats`,
      `/reset`, and the read-only `/static/<filename>` allow-list.
      _R1, R4, R6, R7, R8, R9, R10, R11, R12_

- [ ] 3. Add `tests/test_backend_api.py` (FastAPI TestClient, injected clock):
      H-2 zone membership (haversine); detection response shape and flags;
      response after advancing the clock (no sleep); 75% compliance; `/stats`
      incrementing and `/reset` zeroing; `/brief` default source; 503 when
      `predict` raises (monkeypatched); `/static` rejecting other filenames.
      _R3, R4, R5, R7, R8, R9, R10, R11, R12_

- [ ] 4. Pin the FastAPI stack in `requirements.txt` (fastapi, uvicorn, httpx
      for TestClient) — shared file; heads-up to teammate.
      _R1_

- [ ] 5. Run `ruff check .` and `pytest -q`.
      _R1–R12_

- [x] 6. Add `GET /hydrophones` (expose the 4 hydrophones from `backend/sim.py`
      as `{id,lat,lon,simulated:true}`, positions unchanged) and a test that it
      returns exactly H-1 to H-4 and H-2 matches the `/detections` zone center.
      _R6a_

- [x] 7. Reject a second detection while one is active: add
      `Simulation.has_active_detection()` and a 409 guard in `POST /detections`
      (detail "A detection is already active. Reset first.", no model call, no
      state change). Test: two POSTs in a row — the second is 409 and `/stats`
      still shows 1 detection and 4 alerts.
      _R13_

- [x] 8. Make `GET /brief` live per detection: add read-only
      `Simulation.brief_inputs()` / `active_detection_id()` that expose the
      current `(detection, compliance)` in `build_demo_input()` shape once the
      vessels have responded; call `brief.generate_brief_result` from a sync
      `/brief` route; cache the result in memory keyed by `detection_id`
      (Bedrock at most once per detection) and clear it on `/reset`; return
      `{"brief","source","detection_id","generated_at"}`, falling back to the
      cached file (`source:"cache"`) when the live call isn't `"bedrock"`.
      Tests (mocking `generate_brief_result`): before a detection -> cached
      file; after response -> generated once with the live `detection_id`, a
      second GET doesn't call again; live `source:"cache"` -> cached file;
      `/reset` clears the per-detection cache.
      _R8_