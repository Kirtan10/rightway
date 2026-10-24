# Design — frontend-map

## Files

- `index.html` — structure only: header (whale SVG icon, title, inline tagline,
  centered text tabs "Live bay / Detections / Ship compliance", location pill,
  DEMO DATA badge), two-column Live bay body (map card + cards column),
  Detections and Ship compliance tab panels, footer. Loads pinned Leaflet 1.9.4
  CSS/JS from unpkg, Google Fonts (Inter + JetBrains Mono), then `app.js`.
- `style.css` — dark navy theme (cards `#0d2236`, border `#1e3a52`, radius
  16px), teal accent `#5eead4`, Inter for UI and JetBrains Mono for labels and
  card headers, two-column grid, map overlays (title, buttons, legend pill row),
  status chips, pixelated spectrogram, shimmering idle grid.
- `app.js` — all behavior; `API = "http://localhost:8000"` constant at top.

## Visual style (mockup)

Schematic map with no tiles; a navy gradient backdrop; a simplified land
polygon, faint graticule, a teal shipping-lane band + dashed centerline, a
dashed Stellwagen Bank sanctuary ellipse, place labels, SVG ship icons rotated
by heading, and glowing teal hydrophone dots. The map card carries overlays:
top-left kicker + "Listening to the bay" title, top-right Simulate/Reset
buttons, bottom-left legend pill row.

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

## Map (schematic, no tiles)

Leaflet is kept only for projection, markers, and the zone circle — the tile
layer is removed. Scroll-wheel zoom and dragging are disabled and zoom controls
hidden. The map fills the full width of its card (`#map { width: 100% }`). The
water background is a navy gradient (`#0a1e33` -> `#081626`).

Framing: `fitView()` fits the map to fixed `VIEW_BOUNDS` (41.62–42.62 N,
71.10–69.92 W) so Boston, Plymouth, Cape Cod Bay and the whole Cape (to
Provincetown and Chatham) are always visible — the view no longer tightens to
the markers. `fitView()` runs after vessels render, after hydrophones load, on
returning to the Live bay tab, and on window `resize` (debounced).

Base layers drawn once on load (`drawBaseMap()`): an approximate coastline
`L.polygon` (~60 points, `smoothFactor: 1.5`) running Cape Ann -> Boston
Harbor/Hull -> South Shore -> Plymouth -> Cape Cod Canal -> the Cape's arm east
to Chatham -> up the outer Cape -> the Provincetown hook curling back west; fill
`#0f2a22` @ 0.9, stroke `#2f6b4f` 1.5px. The mainland edge is kept west of the
vessels (Mystic @ lon -71.00) and the Cape arm south/east of them, so land never
covers a vessel or hydrophone. The polygon is closed with two points far
outside the view (`~ -71.40` lon, beyond the lat bounds) so no straight vertical
closing edge is visible. Also: 3 faint graticule curves (`#ffffff` @ 0.04); a
shipping-lane band (fill `#5eead4` @ 0.10, dashed centerline @ 0.35) with the
"Boston shipping lane" label at the EAST end (~42.29, -70.32, beyond Orion Bay)
so it never touches a vessel label; a dashed Stellwagen Bank sanctuary ellipse
centered ~(42.42, -70.33) with lat radius 0.33 / lon radius 0.22 (east of the
cluster, outline only so it does not swallow the lane), its label placed just
inside the TOP of the oval (below the Simulate/Reset buttons); and place labels
(`L.divIcon`): "Boston" (white bold, west of H-1), "Plymouth" (~41.96, -70.72,
on land), "Cape Cod Bay" (~41.88, -70.35, inside the bay), "Cape Cod"
(~41.75, -70.05, on the Cape) in soft green.

Vessels are `L.marker` with an SVG pointed-hull `divIcon` (~22x8). The hull
points right (east) at 0°, so it is rotated by `heading - 90` (heading 90 ->
0°, points right). Colored by status (normal `#e2e8f0`, alerted `#f59e0b`,
complying `#22c55e`, not_complying `#ef4444`), each with a permanent 11px
monospace "Name NN kn" tooltip (dark text-shadow) offset at least 14 px from the
icon center so a label never covers its own icon (Blue Fin II uses "left").
Hydrophones are teal dots (12px, full-opacity `#5eead4`, 2px `#2bb3a0` border,
soft glow) with monospace teal labels. The slow zone is an `L.circle` (amber,
dashed, faint fill) with radius `radius_nm * 1852` meters.

Label de-overlap: `deOverlapLabels()` runs after each render (and refit). It
measures every vessel label's bounding box; fixed obstacles that are never moved
are the hydrophone labels, the place labels, the lane label and the sanctuary
label. Any vessel label overlapping an already-placed or fixed label is rebound
through a sequence of candidate placements (all >= 14 px offsets) until it no
longer collides.

## State and polling

A single `state` object holds the detection, poll timer, and map layers.
Pressing Simulate POSTs the detection, stores it, draws the zone, switches the
spectrogram to the demo image and sets the hydrophone-card status to "Up-call
detected", plays audio, renders the confidence, disables the button, then polls
`/vessels`, `/compliance`, `/stats` every 1 s for 10 s (10 ticks) via
`setInterval`, re-rendering markers and cards each tick. Reset POSTs `/reset`,
clears timers, removes the zone, and returns all cards to idle (hydrophone
status back to "Listening…"). Hydrophone markers persist across detect/reset.

## Tabs

Three text tabs: Live bay (map + right cards), Detections (the detection card),
and Ship compliance (the compliance table). Each tab toggles the `hidden`
attribute on its panel. Because `.panel-live` uses `display: grid`, a global
`[hidden] { display: none !important }` rule ensures a hidden panel actually
disappears (the earlier bug: the grid panel's own `display` overrode the
`hidden` attribute, so the Live bay map showed under every tab). Switching to
Live bay calls `map.invalidateSize()` then re-fits and re-runs de-overlap.

## Cards

1. Hydrophone — header "HYDROPHONE H-1 to H-4 · 50–500 Hz" with a status that
   reads "Listening…" idle and "Up-call detected" after a detection. Idle shows
   a CSS-grid of ~40x12 dim teal squares with random low opacities, gently
   shimmering, with axis labels "0 s" / "background ocean noise" / "2 s". After
   a detection it shows `/static/demo_spectrogram.png` scaled to the box
   (`image-rendering: pixelated`) and the middle axis label becomes "synthetic
   demo clip"; an `<audio>` of `/static/demo_upcall.wav` plays via a caught
   `.play()` promise. (The idle noise PNG is no longer used.)
2. Detection (Detections tab) — "No detections this session." until a detection,
   then `H-2 · confidence ` + `conf.toFixed(2)` plus zone and time.
3. Vessels in the zone — "speed before → now" in the header; idle hint text;
   after detection a row per `vessels_in_zone` with "before → now" (now pulled
   from `/vessels` by id) and a status chip.
4. Brief — label "AI BRIEF · BEDROCK" if `source === "bedrock"` else
   "AI BRIEF · CACHED"; idle body text fixed; after vessels respond (compliance
   not null) show the `/brief` text via `textContent`.
5. Stats — three columns with large numbers: "Detections (sim)", "Alerts sent
   (sim)", "Compliance" ("—" when null, else `${pct}%`).

## Errors and escaping

`api()` wraps `fetch`; on non-OK it reads `{detail}` when present. Each card has
an error slot; a `/detections` 503 shows its detail in the spectrogram card. All
API-derived strings use `textContent`; no `innerHTML` for dynamic data.

## Footer

Exact `product.md` copy: "Prototype: classifier trained on synthetic up-calls,
not real-world accuracy. All vessel data is simulated. Screening aid, not a
replacement for NOAA systems. Map is schematic."
