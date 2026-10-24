# Design — backend-sim

## Modules

- `backend/sim.py` — the simulation state and all domain logic. No FastAPI
  imports, so it is unit-testable on its own.
- `backend/app.py` — the FastAPI app: routes, CORS, static ML assets, and
  wiring to a single `Simulation` instance.

## Clock injection

`Simulation` holds a `clock: Callable[[], float]` (default `time.monotonic`).
Nothing runs in the background. The response transition is computed lazily:
on every read, if a detection exists and `clock() - detection_time >=
SIM_RESPONSE_SECONDS`, vessel speeds/statuses are advanced to their response
values before the response is built. Tests inject a mutable fake clock and
advance it, so no `sleep` is needed.

## State

- `VESSELS`: 9 immutable seed records (id, name, type, lat, lon, heading,
  starting speed). Coordinates lay a lane running roughly east from Boston
  Harbor (~42.33N, -70.90W).
- `HYDROPHONES`: H-1..H-4 with lat/lon. H-2 = (42.335, -70.665).
- Per-vessel mutable runtime: current speed and status
  (`normal|alerted|complying|not_complying`).
- `detection`: the active detection dict + the monotonic time it was created.
- `stats`: `detections`, `alerts_sent` counters (sim events only).

Verified H-2 membership (haversine nm): Nordic Tide 1.5, Harbor Queen 1.9,
Blue Fin II 1.6, Cape Runner 2.9 (all <10); Mystic 15.0, Atlantic Star 13.4,
Orion Bay 15.5, Sea Ledger 13.5, Gull Point 14.8 (all >10).

## Geometry

`haversine_nm(lat1, lon1, lat2, lon2)` returns great-circle distance in nautical
miles (Earth radius 6371.0088 km, 1 nm = 1.852 km). In-zone = distance from the
hydrophone <= `ZONE_RADIUS_NM` (10).

## Detection flow (R4/R5)

1. Resolve `wav` (default `ml/demo_upcall.wav`); reject paths outside `ml/`
   with HTTP 400.
2. `confidence = ml.predict.predict(wav)`. If it raises, the route returns 503
   with the message (R12) and no state changes.
3. Build the 10 nm zone at the hydrophone; vessels within it become `alerted`
   and are recorded as the detection's in-zone set with `speed_before`.
4. Store the detection and its creation time; increment `detections` and add
   the in-zone count to `alerts_sent`.
5. Return the detection payload with `synthetic_demo_clip` and `simulated`.

The response map (applied lazily after `SIM_RESPONSE_SECONDS`) is keyed by
vessel name: Nordic Tide->10 complying, Harbor Queen->10 complying,
Blue Fin II->9 complying, Cape Runner->17 not_complying.

## Compliance (R7)

Before a detection, or before the response time has elapsed, `compliance_pct`
is `null` and `vessels` is empty. After the response: `complying / in-zone *
100` -> 3/4 = 75.0 in the demo. Each vessel row carries before/after/status.

## /brief (R8)

Reads `backend/cache/brief.json` directly and returns it, injecting
`"source":"cache"` if absent. Missing file -> the fixed "not generated yet"
payload. `backend/brief.py` is never imported here.

## Static assets (R11)

A small allow-list route at `/static/{filename}` maps exactly the 4 permitted
filenames to the real files under `ml/` and serves them with `FileResponse`.
Any other filename -> HTTP 404. Files are served in place; `ml/` is untouched.

## Testing

`tests/test_backend_api.py` uses FastAPI `TestClient` with an injected fake
clock: H-2 membership; detection shape/flags; response after advancing the
clock; 75% compliance; `/stats` incrementing and `/reset` zeroing; `/brief`
default source; 503 when `predict` is monkeypatched to raise; `/static`
rejecting other filenames.
