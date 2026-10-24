# Design — frontend-map

## Files

- `index.html` — structure only: header (title, tagline, pill, DEMO DATA badge,
  tabs), two-column body (map column + cards column), compliance tab, footer.
  Loads pinned Leaflet 1.9.4 CSS/JS from unpkg and then `app.js`.
- `style.css` — dark navy theme, teal accent `#5eead4`, desktop-first two-column
  grid, card styling, status chips, legend, tabs, pixelated spectrogram image.
- `app.js` — all behavior; `API = "http://localhost:8000"` constant at top.

## Verified API shapes (from the running backend)

- `GET /vessels` -> `[{id,name,type,lat,lon,heading,speed,status,simulated}]`.
- `POST /detections {hydrophone_id,wav}` -> `{detection_id, hydrophone_id,
  confidence (float ~0.99999), zone{lat,lon,radius_nm:10},
  vessels_in_zone[{id,name,speed_before}], synthetic_demo_clip, simulated}`.
- `GET /compliance` -> `{compliance_pct (null idle / 75.0 after), vessels[{id,
  name,before,after,status}], simulated}`.
- `GET /stats` -> `{detections, alerts_sent, compliance_pct, simulated}`.
- `GET /brief` -> `{brief, source}` (`source` is "cache" in the demo).
- `GET /hydrophones` -> `[{id,lat,lon,simulated:true}]` for H-1 to H-4.
- `GET /static/{filename}` -> the 4 ML assets.

## Hydrophones

The backend exposes `GET /hydrophones` -> `[{id,lat,lon,simulated:true}]` for
H-1 to H-4. On load, `loadHydrophones()` fetches it and draws all four as teal
`circleMarker`s with permanent labels (visible from the start, not only after a
detection). If the request fails, the map renders without hydrophones and the
error is logged to the console; positions are never invented. The earlier
approach of deriving H-2 from the `/detections` zone has been removed.

## Map

Leaflet map, CARTO dark tiles
`https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png` with attribution.
Vessel markers are `L.circleMarker` colored by `STATUS_COLORS`. Each vessel gets
a permanent tooltip "Name NN kn"; tooltip `direction` and `offset` are chosen
from the vessel id via a small deterministic table so labels spread out and do
not overlap at the fit zoom. `fitBounds` over all vessel points plus the four
hydrophone points. The slow zone is an `L.circle` (amber, dashed) with radius
`radius_nm * 1852` meters.

## State and polling

A single `state` object: `{detection, timers}`. Pressing Simulate POSTs the
detection, stores it, draws the zone + H-2 marker, switches the spectrogram,
plays audio, renders the confidence, disables the button, then polls `/vessels`,
`/compliance`, `/stats` every 1 s for 10 s (10 ticks) via `setInterval`,
re-rendering markers and cards each tick. Reset POSTs `/reset`, clears timers,
removes the zone + H-2 marker, and returns all cards to idle.

## Cards

1. Spectrogram — idle `/static/noise_spectrogram.png` "background ocean noise";
   after detection `/static/demo_spectrogram.png` "synthetic demo clip" and an
   `<audio>` of `/static/demo_upcall.wav` with `.play()` wrapped in a caught
   promise. `image-rendering: pixelated`, width 100% of the card.
2. Detection — hidden until detection; `H-2 · confidence ` + `conf.toFixed(2)`.
3. Vessels in the zone — idle hint text; after detection a row per
   `vessels_in_zone` with "before → now" (now pulled from `/vessels` by id) and
   a status chip.
4. Brief — label "AI BRIEF · BEDROCK" if `source === "bedrock"` else
   "AI BRIEF · CACHED"; idle body text fixed; after vessels respond (compliance
   not null) show the `/brief` text via `textContent`.
5. Stats — "Detections (sim)", "Alerts sent (sim)", "Compliance" ("—" when
   null, else `${pct}%`).

## Errors and escaping

`api()` wraps `fetch`; on non-OK it reads `{detail}` when present. Each card has
an error slot; a `/detections` 503 shows its detail in the spectrogram card. All
API-derived strings use `textContent`; no `innerHTML` for dynamic data.

## Footer

Exact `product.md` copy: "Prototype: classifier trained on synthetic up-calls,
not real-world accuracy. All vessel data is simulated. Screening aid, not a
replacement for NOAA systems. Map is schematic."
