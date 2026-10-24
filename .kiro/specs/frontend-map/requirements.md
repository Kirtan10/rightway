# Requirements — frontend-map

## Introduction

A single-page, no-build frontend (plain JS + Leaflet 1.9.4 from unpkg) that
visualizes the simulated Massachusetts Bay bay state from the backend and runs
the whale-call demo. It follows `.kiro/steering/product.md` honesty rules: a
"DEMO DATA" badge, the exact footer copy, confidence shown via `toFixed(2)`
(never a percentage, never hard-coded), the brief label driven by `/brief`
source, and all API text inserted with `textContent`.

Scope: `frontend/` and `.kiro/specs/frontend-map/` only.

## Requirements

### R1 — Static page, pinned deps
THE SYSTEM SHALL ship `frontend/index.html`, `frontend/app.js`,
`frontend/style.css`, using Leaflet 1.9.4 CSS+JS from unpkg (pinned), no
framework and no build step, served with `cd frontend && python -m http.server
5500`. The API base `http://localhost:8000` SHALL be a constant at the top of
`app.js`.

### R2 — Header
THE SYSTEM SHALL show "RightWay", the tagline "Hear the whale. Slow the ship.",
a pill "Massachusetts Bay · 4 hydrophones · 9 vessels", an amber "DEMO DATA"
badge, and tabs "Live bay" and "Ship compliance".

### R3 — Map
THE SYSTEM SHALL render a Leaflet map with CARTO dark tiles (with attribution),
fit to all vessels (and H-2 once known). Vessels are circle markers colored by
status (normal `#cbd5e1`, alerted `#f59e0b`, complying `#22c55e`,
not_complying `#ef4444`) with permanent "Name NN kn" labels whose tooltip
direction/offset vary per vessel id to avoid overlap. A color legend, a
"Simulate whale call" button, and a small "Reset" button are present.

### R4 — Hydrophone markers
THE SYSTEM SHALL render hydrophones as teal circle markers with permanent
labels only from data the API exposes. The backend exposes no hydrophone
endpoint; only H-2's position is derivable from the `/detections` zone. So H-2
SHALL be drawn once a detection exists, and H-1/H-3/H-4 SHALL NOT be fabricated.

### R5 — Right-column cards
THE SYSTEM SHALL show five cards: spectrogram (idle noise image / detection
image + audio), detection ("H-2 · confidence 1.00" via `toFixed(2)`), vessels
in the zone, brief (label by `/brief` source), and stats.

### R6 — Footer
THE SYSTEM SHALL show the exact footer text from `product.md`.

### R7 — Ship compliance tab
THE SYSTEM SHALL show a table from `/compliance` (vessel, before, after, status
chip) with the compliance % above it; "No detection yet." before a detection.

### R8 — Demo flow
WHEN "Simulate whale call" is pressed THE SYSTEM SHALL POST `/detections
{"hydrophone_id":"H-2","wav":"ml/demo_upcall.wav"}`, draw the 10 nm zone as an
amber dashed circle (`radius_nm * 1852` m), switch the spectrogram, play the
demo audio (autoplay errors caught silently), show the confidence, poll
`/vessels`, `/compliance`, `/stats` every 1 s for 10 s, and disable Simulate
while a detection is active. "Reset" SHALL POST `/reset`, remove the circle, and
restore every card to idle.

### R9 — Errors and escaping
IF a request fails THE SYSTEM SHALL show a short error in the relevant card (a
`/detections` 503 detail in the spectrogram card) and never show a made-up
value. All API-derived text SHALL be inserted with `textContent`.
