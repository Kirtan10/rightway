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
demo audio (autoplay errors caught silently), show the confidence, and poll
`/compliance` and `/stats` every 1 s for 10 s (vessel polling is continuous;
see R12). Simulate SHALL stay
disabled from the moment a detection starts until Reset is clicked (not only for
the 10 s polling window). "Reset" SHALL POST `/reset`, remove the circle, and
restore every card to idle.

### R9 — Errors and escaping
IF a request fails THE SYSTEM SHALL show a short error in the relevant card (a
`/detections` 503 detail in the spectrogram card) and never show a made-up
value. IF `POST /detections` returns HTTP 409 THE SYSTEM SHALL show its detail
in the spectrogram card and keep Simulate disabled. All API-derived text SHALL
be inserted with `textContent`.

### R10 — Sanctuary label while zoomed
WHILE zoomed into the detection zone THE SYSTEM SHALL hide the "Stellwagen Bank
sanctuary" label (it clips at the right edge there) and SHALL show it again
after Reset returns to the whole-bay view.

### R11 — Contact vessel (compliance notice)
THE SYSTEM SHALL show a small "Contact" button on each `not_complying` row in
the "Vessels in the zone" card. WHEN pressed it SHALL open a modal titled
"Compliance notice · <vessel name>" with a message built ONLY from API data —
the vessel name, hydrophone, the 10 nm slow zone, the vessel's speed before and
now, the 10-knot limit, and a polite request to slow to 10 knots or less — ending
with the line "Simulated notice: RightWay demo data". The modal SHALL offer
"Copy message" (clipboard, with a "Copied" confirmation) and "Open email draft"
(a `mailto:` with URL-encoded subject and body and NO recipient address), and
SHALL dismiss on Esc or a Close button. The dialog SHALL use `role="dialog"`,
`aria-modal="true"`, be keyboard-focusable, and trap focus. After the notice is
copied or opened, that vessel's row SHALL read "Notice sent (sim)" until Reset,
and a "Notices sent (sim)" count under the stats SHALL increment; Reset SHALL
clear it. THE SYSTEM SHALL never send anything automatically.

### R12 — Live ship movement
THE SYSTEM SHALL poll `GET /vessels` every 1 second at all times (before and
after any detection, and after Reset), and SHALL move the existing markers with
`setLatLng`, update each marker's rotation (from the current heading) and its
"Name NN kn" label text in place, WITHOUT rebuilding the marker layer on every
tick. A full marker rebuild SHALL happen only on a structural change (the idle
<-> zone label set flips). THE SYSTEM SHALL re-run the label de-overlap pass at
most once every 3 seconds (not every tick). THE SYSTEM SHALL show a small mono
label in the map's bottom-right corner reading "Simulated · time ×60".
