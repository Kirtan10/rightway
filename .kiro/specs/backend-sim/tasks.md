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
