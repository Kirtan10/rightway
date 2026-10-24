"use strict";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const API = "http://localhost:8000";

const STATUS_COLORS = {
  normal: "#e2e8f0",
  alerted: "#f59e0b",
  complying: "#22c55e",
  not_complying: "#ef4444",
};

// Per-vessel tooltip placement so permanent labels don't overlap at fit zoom.
// Keyed by vessel id; direction + pixel offset spread the labels around.
// Offsets are at least 14 px from the icon center so a label never covers its
// own icon.
const LABEL_PLACEMENT = {
  "V-1": { direction: "left", offset: [-14, 0] },   // Mystic (west)
  "V-2": { direction: "right", offset: [14, 0] },   // Atlantic Star (far east)
  "V-3": { direction: "bottom", offset: [0, 14] },  // Orion Bay (far east)
  "V-4": { direction: "left", offset: [-14, 0] },   // Blue Fin II (cluster)
  "V-5": { direction: "top", offset: [0, -14] },    // Nordic Tide (cluster)
  "V-6": { direction: "left", offset: [-14, 8] },   // Harbor Queen (cluster)
  "V-7": { direction: "right", offset: [14, 0] },   // Cape Runner (cluster)
  "V-8": { direction: "top", offset: [0, -14] },    // Sea Ledger (north)
  "V-9": { direction: "bottom", offset: [0, 14] },  // Gull Point (south)
};
const DEFAULT_PLACEMENT = { direction: "top", offset: [0, -14] };

// The 4 vessels clustered around H-2 (also the in-zone set in the demo). In the
// idle whole-bay view their individual labels are replaced by one "4 vessels"
// label near H-2 to avoid crowding; when zoomed into the zone they show.
const CLUSTER_IDS = new Set(["V-4", "V-5", "V-6", "V-7"]);

const STATIC = {
  demo: `${API}/static/demo_spectrogram.png`,
  audio: `${API}/static/demo_upcall.wav`,
};

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const state = {
  detection: null, // last /detections response
  pollTimer: null,
  vesselLayer: null, // L.layerGroup of vessel markers
  zoneCircle: null,
  hydrophoneLayer: null, // L.layerGroup of hydrophone markers
  hydrophones: [], // [{id,lat,lon,simulated}] from GET /hydrophones
  zoomMode: "idle", // "idle" (whole bay) or "zone" (flown into a detection)
};

// ---------------------------------------------------------------------------
// DOM helpers
// ---------------------------------------------------------------------------
const $ = (id) => document.getElementById(id);

function showError(id, message) {
  const el = $(id);
  el.textContent = message;
  el.hidden = false;
}
function clearError(id) {
  const el = $(id);
  el.textContent = "";
  el.hidden = true;
}

async function api(path, options) {
  const res = await fetch(`${API}${path}`, options);
  let body = null;
  try {
    body = await res.json();
  } catch (_e) {
    body = null;
  }
  if (!res.ok) {
    const detail = body && body.detail ? body.detail : `HTTP ${res.status}`;
    const err = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    err.status = res.status;
    throw err;
  }
  return body;
}

// ---------------------------------------------------------------------------
// Map (schematic — no tiles)
// ---------------------------------------------------------------------------
const map = L.map("map", {
  zoomControl: false,
  attributionControl: false,
  scrollWheelZoom: false,
  dragging: false,
  doubleClickZoom: false,
  boxZoom: false,
  keyboard: false,
  touchZoom: false,
});

// Fixed view bounds so Boston, Plymouth, Cape Cod Bay and the whole Cape
// (Provincetown and Chatham) are always visible.
const VIEW_BOUNDS = L.latLngBounds([41.62, -71.1], [42.62, -69.92]);
map.fitBounds(VIEW_BOUNDS);

// Approximate Massachusetts coastline (schematic, ~70 points). Mainland edge is
// kept west of the vessels (Mystic is at lon -71.00); the Cape's arm runs south
// and east of them, so land never covers a vessel or hydrophone.
// Order: Cape Ann -> Boston Harbor/Hull -> South Shore -> Plymouth -> Canal ->
// Cape arm east to Chatham -> up the outer Cape -> Provincetown hook (curls
// back west) -> close down the far-left edge.
const COASTLINE = [
  // North mainland / Cape Ann, down the shore toward Boston (kept west of -71.0)
  [42.62, -70.78],
  [42.60, -70.83],
  [42.57, -70.87],
  [42.54, -70.90],
  [42.51, -70.93],
  [42.48, -70.96],
  [42.45, -70.99],
  [42.43, -71.02],
  [42.41, -71.04],
  [42.39, -71.05], // Boston Harbor (west of Mystic @ -71.00)
  [42.37, -71.05],
  [42.355, -71.04], // harbor mouth
  [42.34, -71.02],
  [42.325, -71.00], // Hull peninsula curling out
  [42.31, -70.98],
  [42.30, -70.95],
  [42.285, -70.93], // Nantasket / South Shore
  [42.27, -70.90],
  [42.24, -70.86],
  [42.21, -70.83], // Scituate
  [42.17, -70.80],
  [42.13, -70.78],
  [42.09, -70.76],
  [42.05, -70.74], // Plymouth
  [42.01, -70.72],
  [41.97, -70.70],
  [41.93, -70.68], // toward the canal
  [41.90, -70.66],
  [41.87, -70.63],
  [41.84, -70.60], // Cape Cod Canal (west end)
  [41.80, -70.56],
  [41.77, -70.52],
  [41.75, -70.46], // upper Cape, arm turning east
  [41.74, -70.38],
  [41.73, -70.30],
  [41.72, -70.22],
  [41.71, -70.14],
  [41.70, -70.06],
  [41.69, -69.99], // toward Chatham (outer elbow)
  [41.70, -69.95],
  [41.74, -69.94],
  [41.80, -69.95], // up the outer Cape (Atlantic side)
  [41.86, -69.97],
  [41.92, -70.00],
  [41.98, -70.02],
  [42.03, -70.06],
  [42.06, -70.11], // approaching the hook
  [42.075, -70.17],
  [42.07, -70.22], // Provincetown hook tip
  [42.055, -70.24],
  [42.04, -70.22],
  [42.035, -70.17], // inside of the hook, curling back west
  [42.02, -70.14],
  [41.98, -70.16],
  [41.93, -70.22], // bay (inner) side of the Cape arm
  [41.88, -70.30],
  [41.83, -70.40],
  [41.80, -70.50],
  [41.79, -70.58],
  // Close the polygon far outside the visible area (well west of the view and
  // beyond the lat bounds) so no straight closing edge is ever visible, even
  // when zoomed in on a detection at any card width.
  [41.00, -72.50],
  [43.20, -72.50],
];

function drawBaseMap() {
  // Land polygon (smoothed).
  L.polygon(COASTLINE, {
    color: "#2f6b4f",
    weight: 1.5,
    fillColor: "#0f2a22",
    fillOpacity: 0.9,
    smoothFactor: 1.5,
    interactive: false,
  }).addTo(map);

  // Faint graticule: a few low-opacity horizontal curves across the water.
  const graticuleLats = [42.5, 42.2, 41.9];
  for (const lat of graticuleLats) {
    const pts = [];
    for (let lon = -71.1; lon <= -69.9; lon += 0.1) {
      pts.push([lat + 0.04 * Math.sin((lon + 71) * 2.5), lon]);
    }
    L.polyline(pts, { color: "#ffffff", weight: 1, opacity: 0.04, interactive: false }).addTo(map);
  }

  // Shipping lane band (~3 nm wide) from Boston Harbor east past the vessels.
  const laneWest = [42.36, -70.95];
  const laneEast = [42.30, -70.3];
  const halfWidthDeg = 0.025; // ~1.5 nm each side
  const lanePoly = [
    [laneWest[0] + halfWidthDeg, laneWest[1]],
    [laneEast[0] + halfWidthDeg, laneEast[1]],
    [laneEast[0] - halfWidthDeg, laneEast[1]],
    [laneWest[0] - halfWidthDeg, laneWest[1]],
  ];
  L.polygon(lanePoly, {
    stroke: false,
    fillColor: "#5eead4",
    fillOpacity: 0.1,
    interactive: false,
  }).addTo(map);
  L.polyline([laneWest, laneEast], {
    color: "#5eead4",
    opacity: 0.35,
    weight: 1.5,
    dashArray: "5 7",
    interactive: false,
  }).addTo(map);
  // Lane label at the EAST end of the band, beyond Orion Bay (-70.34), so it
  // never touches a vessel label.
  placeDivLabel(42.29, -70.32, "Boston shipping lane", "lane-label");

  // Stellwagen Bank sanctuary: dashed teal ellipse outline (no fill), centered
  // over the bank and east of the vessel cluster so it doesn't swallow the lane.
  const sancLat = 42.42;
  const sancLon = -70.33;
  const sancRLat = 0.33;
  const sancRLon = 0.22;
  placeEllipse(sancLat, sancLon, sancRLat, sancRLon, {
    color: "#5eead4",
    opacity: 0.35,
    weight: 1.5,
    dashArray: "4 7",
    fill: false,
    interactive: false,
  });
  // Label on the RIGHT side of the oval so it never sits behind the top-right
  // Simulate/Reset buttons.
  placeDivLabel(42.42, -70.05, "Stellwagen Bank sanctuary", "sanctuary-label");

  // Place labels. Boston sits west of H-1 (42.345, -70.930) on the mainland.
  placeDivLabel(42.40, -71.00, "Boston", "place-label city");
  placeDivLabel(41.96, -70.72, "Plymouth", "place-label area");
  placeDivLabel(41.88, -70.35, "Cape Cod Bay", "place-label area");
  placeDivLabel(41.75, -70.05, "Cape Cod", "place-label area");
}

function placeEllipse(lat, lon, rLat, rLon, style) {
  const pts = [];
  for (let a = 0; a <= 360; a += 10) {
    const r = (a * Math.PI) / 180;
    pts.push([lat + rLat * Math.sin(r), lon + rLon * Math.cos(r)]);
  }
  L.polyline(pts, style).addTo(map);
}

function placeDivLabel(lat, lon, text, className) {
  const icon = L.divIcon({ className, html: "", iconSize: null });
  const marker = L.marker([lat, lon], { icon, interactive: false, keyboard: false });
  marker.addTo(map);
  // Set text safely (no innerHTML of API data; these are static strings, but
  // keep the escaping discipline consistent).
  const el = marker.getElement();
  if (el) el.textContent = text;
  else marker.once("add", () => { marker.getElement().textContent = text; });
  // Remember map labels (place/lane/sanctuary) as fixed obstacles for de-overlap.
  (state.fixedLabelMarkers = state.fixedLabelMarkers || []).push(marker);
  return marker;
}

// Pointed-hull ship icon (~22x8). The hull points RIGHT (east) at 0deg, so a
// compass heading maps to rotate(heading - 90): heading 90 (east) -> 0deg
// (points right), heading 0 (north) -> -90deg (points up).
function vesselIcon(color, heading) {
  const deg = (Number(heading) || 0) - 90; // numeric from API; coerce defensively
  const svg =
    `<svg width="22" height="8" viewBox="0 0 22 8" ` +
    `style="transform:rotate(${deg}deg)">` +
    `<path d="M1 4 L13 1 L21 4 L13 7 Z" fill="${color}" ` +
    `stroke="#04101c" stroke-width="0.6"/></svg>`;
  return L.divIcon({ className: "vessel-icon", html: svg, iconSize: [22, 8], iconAnchor: [11, 4] });
}

// IDs of vessels currently inside the detection zone (empty when idle).
function inZoneIds() {
  if (!state.detection) return new Set();
  return new Set(state.detection.vessels_in_zone.map((v) => v.id));
}

function renderVessels(vessels) {
  if (state.vesselLayer) {
    state.vesselLayer.remove();
  }
  state.vesselLayer = L.layerGroup().addTo(map);
  state.vesselMarkers = [];

  const zoomed = state.zoomMode === "zone";
  const inZone = inZoneIds();

  for (const v of vessels) {
    const color = STATUS_COLORS[v.status] || STATUS_COLORS.normal;
    const marker = L.marker([v.lat, v.lon], {
      icon: vesselIcon(color, v.heading),
      keyboard: false,
    });

    // Decide whether this vessel gets an individual label.
    // Idle whole-bay view: hide cluster labels (replaced by one "4 vessels"
    // label near H-2); show the rest. Zoomed-in: show every vessel label.
    const showLabel = zoomed || !CLUSTER_IDS.has(v.id);
    if (showLabel) {
      const place = LABEL_PLACEMENT[v.id] || DEFAULT_PLACEMENT;
      const label = `${v.name} ${v.speed} kn`;
      marker.bindTooltip(label, {
        permanent: true,
        direction: place.direction,
        offset: place.offset,
        className: "vessel-label",
      });
      marker._labelText = label; // remember for de-overlap rebinding
      // In-zone labels must always stay visible (never hidden by de-overlap).
      marker._protected = zoomed && inZone.has(v.id);
    }
    marker.addTo(state.vesselLayer);
    state.vesselMarkers.push(marker);
  }

  // Combined "4 vessels" label near H-2 in the idle view only.
  updateClusterLabel(!zoomed);

  state.lastVessels = vessels;
  // Let Leaflet lay out the tooltips, then nudge any that overlap.
  requestAnimationFrame(() => deOverlapLabels());
}

// A single "4 vessels" divIcon near H-2, shown only in the idle whole-bay view.
function updateClusterLabel(show) {
  if (state.clusterLabel) {
    state.clusterLabel.remove();
    state.clusterLabel = null;
  }
  if (!show) return;
  const h2 = (state.hydrophones || []).find((h) => h.id === "H-2");
  if (!h2) return;
  const icon = L.divIcon({ className: "vessel-label cluster-count", html: "", iconSize: null });
  const marker = L.marker([h2.lat - 0.03, h2.lon], { icon, interactive: false, keyboard: false });
  marker.addTo(map);
  const el = marker.getElement();
  if (el) el.textContent = "4 vessels";
  else marker.once("add", () => { marker.getElement().textContent = "4 vessels"; });
  state.clusterLabel = marker;
}

// Fit the map to the fixed VIEW_BOUNDS (Boston -> whole Cape). Called on
// render, on resize, and on returning to the Live bay tab.
function fitView() {
  map.fitBounds(VIEW_BOUNDS, { animate: false });
}

// Candidate tooltip placements to try, in order, when a label overlaps another.
// All offsets are >= 14 px so a nudged label still clears its own icon.
const LABEL_TRIES = [
  { direction: "right", offset: [14, 0] },
  { direction: "left", offset: [-14, 0] },
  { direction: "top", offset: [0, -14] },
  { direction: "bottom", offset: [0, 14] },
  { direction: "right", offset: [14, -18] },
  { direction: "left", offset: [-14, 18] },
];

function rectsOverlap(a, b) {
  return !(a.right < b.left || b.right < a.left || a.bottom < b.top || b.bottom < a.top);
}

function labelRect(marker) {
  const tip = marker.getTooltip();
  const el = tip && tip.getElement();
  return el ? el.getBoundingClientRect() : null;
}

function rebindLabel(marker, direction, offset) {
  marker.unbindTooltip();
  marker.bindTooltip(marker._labelText, {
    permanent: true,
    direction,
    offset,
    className: "vessel-label",
  });
}

// After markers render, measure label bounding boxes and nudge overlapping ones
// by cycling through LABEL_TRIES. Fixed obstacles (never moved): hydrophone
// labels, place labels, the lane label, the sanctuary label, and the combined
// "4 vessels" label. In-zone (protected) vessel labels are placed first and
// kept; other vessel labels that still collide after trying every placement are
// hidden (so the zoomed view stays readable).
function deOverlapLabels() {
  const occupied = [];
  // Hydrophone labels are tooltip-based.
  for (const m of state.hydrophoneMarkers || []) {
    const r = labelRect(m);
    if (r) occupied.push(r);
  }
  // Place / lane / sanctuary labels are element-based divIcons.
  for (const m of state.fixedLabelMarkers || []) {
    const el = m.getElement();
    if (el) occupied.push(el.getBoundingClientRect());
  }
  // The combined "4 vessels" label (idle view) is also a fixed obstacle.
  if (state.clusterLabel && state.clusterLabel.getElement()) {
    occupied.push(state.clusterLabel.getElement().getBoundingClientRect());
  }

  const collides = (r) => r && occupied.some((o) => rectsOverlap(r, o));

  // Only vessels that currently have a tooltip participate.
  const labelled = (state.vesselMarkers || []).filter((m) => m.getTooltip());
  // Protected (in-zone) labels first so they always win a spot.
  const ordered = [
    ...labelled.filter((m) => m._protected),
    ...labelled.filter((m) => !m._protected),
  ];

  for (const marker of ordered) {
    let rect = labelRect(marker);
    if (collides(rect)) {
      let resolved = false;
      for (const t of LABEL_TRIES) {
        rebindLabel(marker, t.direction, t.offset);
        rect = labelRect(marker);
        if (!collides(rect)) {
          resolved = true;
          break;
        }
      }
      // Still overlapping: protected labels stay (readability of the zone
      // matters most); non-protected labels are hidden.
      if (!resolved && !marker._protected) {
        marker.closeTooltip();
        marker.unbindTooltip();
        continue;
      }
    }
    if (rect) occupied.push(rect);
  }
}

async function loadHydrophones() {
  // Draw all four hydrophones on load. If the request fails, show the map
  // without them and log the error — never invent positions.
  try {
    const hydrophones = await api("/hydrophones");
    state.hydrophones = hydrophones;
    if (state.hydrophoneLayer) state.hydrophoneLayer.remove();
    state.hydrophoneLayer = L.layerGroup().addTo(map);
    state.hydrophoneMarkers = [];
    for (const h of hydrophones) {
      // Larger translucent circle behind each dot for a soft glow.
      L.circleMarker([h.lat, h.lon], {
        radius: 12,
        stroke: false,
        fillColor: "#5eead4",
        fillOpacity: 0.18,
        interactive: false,
      }).addTo(state.hydrophoneLayer);
      // The crisp, always-round dot.
      const marker = L.circleMarker([h.lat, h.lon], {
        radius: 6,
        color: "#2bb3a0",
        weight: 2,
        fillColor: "#5eead4",
        fillOpacity: 1,
      });
      // H-4 label goes below to avoid colliding with the lane label.
      const dir = h.id === "H-4" ? "bottom" : "right";
      const off = h.id === "H-4" ? [0, 10] : [8, 0];
      marker.bindTooltip(h.id, {
        permanent: true,
        direction: dir,
        offset: off,
        className: "hydrophone-label",
      });
      marker.addTo(state.hydrophoneLayer);
      state.hydrophoneMarkers.push(marker);
    }
    // Now that hydrophone markers exist, re-run de-overlap against them.
    fitView();
    requestAnimationFrame(() => deOverlapLabels());
  } catch (e) {
    state.hydrophones = [];
    console.error("Failed to load hydrophones:", e.message);
  }
}

function drawZone(detection) {
  const { lat, lon, radius_nm } = detection.zone;
  if (state.zoneCircle) state.zoneCircle.remove();
  state.zoneCircle = L.circle([lat, lon], {
    radius: radius_nm * 1852, // nautical miles -> meters
    color: "#f59e0b",
    weight: 2,
    dashArray: "6 8",
    fillColor: "#f59e0b",
    fillOpacity: 0.08,
    interactive: false,
  }).addTo(map);
  // Hydrophones (incl. H-2) are drawn on load from /hydrophones.
}

function clearZone() {
  if (state.zoneCircle) {
    state.zoneCircle.remove();
    state.zoneCircle = null;
  }
}

// ---------------------------------------------------------------------------
// Cards
// ---------------------------------------------------------------------------
function buildSpecGrid() {
  const grid = $("spec-grid");
  grid.replaceChildren();
  const cells = 40 * 12;
  for (let i = 0; i < cells; i += 1) {
    const cell = document.createElement("i");
    const o = (0.05 + Math.random() * 0.22).toFixed(3);
    cell.style.setProperty("--o", o);
    cell.style.animationDelay = `${(Math.random() * 2.6).toFixed(2)}s`;
    grid.append(cell);
  }
}

function setSpectrogramIdle() {
  $("spec-grid").hidden = false;
  $("spec-img").hidden = true;
  $("spec-img").removeAttribute("src");
  $("spec-caption").textContent = "background ocean noise";
  $("hydro-status").textContent = "Listening\u2026";
  clearError("spec-error");
}

function setSpectrogramDetected() {
  $("spec-grid").hidden = true;
  $("spec-img").src = STATIC.demo;
  $("spec-img").hidden = false;
  $("spec-caption").textContent = "synthetic demo clip";
  $("hydro-status").textContent = "Up-call detected";
  const audio = $("demo-audio");
  audio.src = STATIC.audio;
  const p = audio.play();
  if (p && typeof p.catch === "function") {
    p.catch(() => {}); // autoplay may be blocked; ignore silently
  }
}

function renderDetectionCard(detection) {
  // Confidence from the API only, 2 decimals, never a percentage.
  const conf = Number(detection.confidence).toFixed(2);
  const zone = detection.zone;
  const time = new Date().toLocaleTimeString();
  $("detection-line").textContent =
    `${detection.hydrophone_id} \u00B7 confidence ${conf} \u00B7 ` +
    `zone ${zone.radius_nm} nm @ ${zone.lat.toFixed(3)}, ${zone.lon.toFixed(3)} \u00B7 ${time}`;
}

function setDetectionIdle() {
  $("detection-line").textContent = "No detections this session.";
}

function renderZoneList(detection, vessels) {
  const host = $("zone-list");
  host.replaceChildren();
  const byId = {};
  for (const v of vessels) byId[v.id] = v;

  for (const entry of detection.vessels_in_zone) {
    const live = byId[entry.id];
    const now = live ? live.speed : entry.speed_before;
    const status = live ? live.status : "alerted";

    const row = document.createElement("div");
    row.className = "zone-row";

    const name = document.createElement("span");
    name.className = "zone-name";
    name.textContent = entry.name;

    const speed = document.createElement("span");
    speed.className = "zone-speed";
    speed.textContent = `${entry.speed_before} → ${now} kn`;

    const chip = document.createElement("span");
    chip.className = `chip ${status}`;
    chip.textContent = status.replace("_", " ");

    const right = document.createElement("span");
    right.style.display = "flex";
    right.style.alignItems = "center";
    right.style.gap = "10px";
    right.append(speed, chip);

    row.append(name, right);
    host.append(row);
  }
}

function renderZoneIdle() {
  const host = $("zone-list");
  host.replaceChildren();
  const p = document.createElement("p");
  p.className = "hint";
  p.textContent = "No active slow zone. Press \u201CSimulate whale call\u201D.";
  host.append(p);
}

async function refreshBrief(responded) {
  try {
    const brief = await api("/brief");
    $("brief-label").textContent =
      brief.source === "bedrock" ? "AI BRIEF \u00B7 BEDROCK" : "AI BRIEF \u00B7 CACHED";
    if (responded) {
      $("brief-body").textContent = brief.brief;
    }
    clearError("brief-error");
  } catch (e) {
    showError("brief-error", `Brief unavailable: ${e.message}`);
  }
}

function setBriefIdle() {
  $("brief-body").textContent =
    "Simulated feed: four hydrophones listening. No up-calls detected this session.";
  clearError("brief-error");
}

function renderStats(stats) {
  $("stat-detections").textContent = String(stats.detections);
  $("stat-alerts").textContent = String(stats.alerts_sent);
  $("stat-compliance").textContent =
    stats.compliance_pct == null ? "\u2014" : `${stats.compliance_pct}%`;
}

function renderComplianceTab(data) {
  $("compliance-pct").textContent =
    data.compliance_pct == null ? "" : `Compliance: ${data.compliance_pct}%`;

  const host = $("compliance-table");
  host.replaceChildren();

  if (data.compliance_pct == null || !data.vessels.length) {
    const p = document.createElement("p");
    p.className = "hint";
    p.textContent = "No detection yet.";
    host.append(p);
    return;
  }

  const table = document.createElement("table");
  table.className = "ctable";
  const thead = document.createElement("thead");
  const htr = document.createElement("tr");
  for (const h of ["Vessel", "Before", "After", "Status"]) {
    const th = document.createElement("th");
    th.textContent = h;
    htr.append(th);
  }
  thead.append(htr);
  table.append(thead);

  const tbody = document.createElement("tbody");
  for (const row of data.vessels) {
    const tr = document.createElement("tr");

    const name = document.createElement("td");
    name.textContent = row.name;

    const before = document.createElement("td");
    before.className = "num";
    before.textContent = `${row.before} kn`;

    const after = document.createElement("td");
    after.className = "num";
    after.textContent = `${row.after} kn`;

    const statusTd = document.createElement("td");
    const chip = document.createElement("span");
    chip.className = `chip ${row.status}`;
    chip.textContent = row.status.replace("_", " ");
    statusTd.append(chip);

    tr.append(name, before, after, statusTd);
    tbody.append(tr);
  }
  table.append(tbody);
  host.append(table);
}

// ---------------------------------------------------------------------------
// Polling / refresh
// ---------------------------------------------------------------------------
async function refreshAll() {
  // Vessels + map
  try {
    const vessels = await api("/vessels");
    renderVessels(vessels);
    if (state.detection) renderZoneList(state.detection, vessels);
    clearError("zone-error");
  } catch (e) {
    showError("zone-error", `Vessels unavailable: ${e.message}`);
  }

  // Compliance (drives brief reveal + compliance tab)
  let responded = false;
  try {
    const comp = await api("/compliance");
    responded = comp.compliance_pct != null;
    renderComplianceTab(comp);
    clearError("compliance-error");
  } catch (e) {
    showError("compliance-error", `Compliance unavailable: ${e.message}`);
  }

  // Stats
  try {
    const stats = await api("/stats");
    renderStats(stats);
    clearError("stats-error");
  } catch (e) {
    showError("stats-error", `Stats unavailable: ${e.message}`);
  }

  // Brief label always; body only once vessels have responded
  await refreshBrief(responded);
}

function startPolling() {
  stopPolling();
  let ticks = 0;
  state.pollTimer = setInterval(async () => {
    ticks += 1;
    await refreshAll();
    if (ticks >= 10) stopPolling(); // ~10 s
  }, 1000);
}

function stopPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
}

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------
async function simulate() {
  $("simulate-btn").disabled = true;
  clearError("spec-error");
  try {
    const detection = await api("/detections", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ hydrophone_id: "H-2", wav: "ml/demo_upcall.wav" }),
    });
    state.detection = detection;
    state.zoomMode = "zone";
    drawZone(detection);
    setSpectrogramDetected();
    renderDetectionCard(detection);
    // Fly into the slow zone so every in-zone vessel label is readable.
    map.flyToBounds(state.zoneCircle.getBounds(), { padding: [60, 60], duration: 1.2 });
    await refreshAll(); // immediate update (re-renders labels in zone mode)
    startPolling(); // then every 1 s for 10 s
  } catch (e) {
    // A 503 (or any failure) from /detections surfaces in the spectrogram card.
    showError("spec-error", `Detection failed: ${e.message}`);
    state.detection = null;
    $("simulate-btn").disabled = false;
  }
}

async function reset() {
  stopPolling();
  try {
    await api("/reset", { method: "POST" });
  } catch (e) {
    showError("stats-error", `Reset failed: ${e.message}`);
  }
  state.detection = null;
  state.zoomMode = "idle";
  clearZone();
  setSpectrogramIdle();
  setDetectionIdle();
  renderZoneIdle();
  setBriefIdle();
  $("simulate-btn").disabled = false;
  // Fly back out to the whole-bay view.
  map.flyToBounds(VIEW_BOUNDS, { duration: 1.2 });
  await refreshAll(); // re-draw normal vessels + zeroed stats
}

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------
function initTabs() {
  const tabs = document.querySelectorAll(".tab");
  tabs.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabs.forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      const which = btn.dataset.tab;
      document.querySelector('[data-panel="live"]').hidden = which !== "live";
      document.querySelector('[data-panel="detections"]').hidden = which !== "detections";
      document.querySelector('[data-panel="compliance"]').hidden = which !== "compliance";
      if (which === "live") {
        // Leaflet needs a size recalculation when its panel was hidden; then
        // re-fit the view and re-run label de-overlap at the real size.
        setTimeout(() => {
          map.invalidateSize();
          fitView();
          requestAnimationFrame(() => deOverlapLabels());
        }, 50);
      }
    });
  });
}

// Re-fit the map (and nudge labels) when the window is resized.
let resizeTimer = null;
window.addEventListener("resize", () => {
  if (resizeTimer) clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    map.invalidateSize();
    fitView();
    requestAnimationFrame(() => deOverlapLabels());
  }, 150);
});

// After any map movement settles (including flyToBounds flights), re-run the
// label de-overlap pass at the new zoom.
map.on("moveend", () => {
  requestAnimationFrame(() => deOverlapLabels());
});

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
function init() {
  initTabs();
  $("simulate-btn").addEventListener("click", simulate);
  $("reset-btn").addEventListener("click", reset);

  drawBaseMap();
  buildSpecGrid();

  setSpectrogramIdle();
  renderZoneIdle();
  setBriefIdle();
  setDetectionIdle();

  // Draw all four hydrophones on load, then the initial (idle) bay state.
  loadHydrophones().then(refreshAll);
}

init();
