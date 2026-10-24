"use strict";

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------
const API = "http://localhost:8000";

const STATUS_COLORS = {
  normal: "#cbd5e1",
  alerted: "#f59e0b",
  complying: "#22c55e",
  not_complying: "#ef4444",
};

// Per-vessel tooltip placement so permanent labels don't overlap at fit zoom.
// Keyed by vessel id; direction + pixel offset spread the labels around.
const LABEL_PLACEMENT = {
  "V-1": { direction: "left", offset: [-8, 0] },    // Mystic (west)
  "V-2": { direction: "right", offset: [8, 0] },    // Atlantic Star (far east)
  "V-3": { direction: "bottom", offset: [0, 8] },   // Orion Bay (far east)
  "V-4": { direction: "bottom", offset: [0, 10] },  // Blue Fin II (cluster)
  "V-5": { direction: "top", offset: [0, -10] },    // Nordic Tide (cluster)
  "V-6": { direction: "left", offset: [-10, 6] },   // Harbor Queen (cluster)
  "V-7": { direction: "right", offset: [10, 0] },   // Cape Runner (cluster)
  "V-8": { direction: "top", offset: [0, -8] },     // Sea Ledger (north)
  "V-9": { direction: "bottom", offset: [0, 8] },   // Gull Point (south)
};
const DEFAULT_PLACEMENT = { direction: "top", offset: [0, -8] };

const STATIC = {
  noise: `${API}/static/noise_spectrogram.png`,
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
// Map
// ---------------------------------------------------------------------------
const map = L.map("map", { zoomControl: true, attributionControl: true });

L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
  attribution:
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
  subdomains: "abcd",
  maxZoom: 19,
}).addTo(map);

map.setView([42.33, -70.7], 10); // provisional; refined by fitBounds

function renderVessels(vessels) {
  if (state.vesselLayer) {
    state.vesselLayer.remove();
  }
  state.vesselLayer = L.layerGroup().addTo(map);

  const points = [];
  for (const v of vessels) {
    const color = STATUS_COLORS[v.status] || STATUS_COLORS.normal;
    const marker = L.circleMarker([v.lat, v.lon], {
      radius: 7,
      color: "#0b1220",
      weight: 1.5,
      fillColor: color,
      fillOpacity: 0.95,
    });
    const place = LABEL_PLACEMENT[v.id] || DEFAULT_PLACEMENT;
    // Label text uses only API values; bound as a Leaflet tooltip (text, escaped).
    const label = `${v.name} ${v.speed} kn`;
    marker.bindTooltip(label, {
      permanent: true,
      direction: place.direction,
      offset: place.offset,
      className: "vessel-label",
    });
    marker.addTo(state.vesselLayer);
    points.push([v.lat, v.lon]);
  }

  for (const h of state.hydrophones) {
    points.push([h.lat, h.lon]);
  }
  if (points.length) {
    map.fitBounds(points, { padding: [40, 40], maxZoom: 11 });
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
    for (const h of hydrophones) {
      const marker = L.circleMarker([h.lat, h.lon], {
        radius: 6,
        color: "#5eead4",
        weight: 2,
        fillColor: "#5eead4",
        fillOpacity: 0.6,
      });
      marker.bindTooltip(h.id, {
        permanent: true,
        direction: "right",
        offset: [8, 0],
        className: "hydrophone-label",
      });
      marker.addTo(state.hydrophoneLayer);
    }
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
function setSpectrogramIdle() {
  $("spec-img").src = STATIC.noise;
  $("spec-caption").textContent = "background ocean noise";
  clearError("spec-error");
}

function setSpectrogramDetected() {
  $("spec-img").src = STATIC.demo;
  $("spec-caption").textContent = "synthetic demo clip";
  const audio = $("demo-audio");
  audio.src = STATIC.audio;
  const p = audio.play();
  if (p && typeof p.catch === "function") {
    p.catch(() => {}); // autoplay may be blocked; ignore silently
  }
}

function renderDetectionCard(detection) {
  $("detection-card").hidden = false;
  // Confidence from the API only, 2 decimals, never a percentage.
  const conf = Number(detection.confidence).toFixed(2);
  $("detection-line").textContent = `${detection.hydrophone_id} · confidence ${conf}`;
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
    drawZone(detection);
    setSpectrogramDetected();
    renderDetectionCard(detection);
    await refreshAll(); // immediate update
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
  clearZone();
  setSpectrogramIdle();
  $("detection-card").hidden = true;
  $("detection-line").textContent = "";
  renderZoneIdle();
  setBriefIdle();
  $("simulate-btn").disabled = false;
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
      document.querySelector('[data-panel="compliance"]').hidden = which !== "compliance";
      if (which === "live") {
        // Leaflet needs a size recalculation when its panel was hidden.
        setTimeout(() => map.invalidateSize(), 50);
      }
    });
  });
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
function init() {
  initTabs();
  $("simulate-btn").addEventListener("click", simulate);
  $("reset-btn").addEventListener("click", reset);

  setSpectrogramIdle();
  renderZoneIdle();
  setBriefIdle();
  $("detection-card").hidden = true;

  // Draw all four hydrophones on load, then the initial (idle) bay state.
  loadHydrophones().then(refreshAll);
}

init();
