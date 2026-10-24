"""Vessel-traffic simulation for RightWay (no FastAPI imports).

All vessel data is SIMULATED. Confidence values are never produced here; the
API layer obtains them from ml.predict.predict. The response transition after a
detection is computed lazily on read using an injectable clock, so there are no
background threads and tests can advance time deterministically.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ML_DIR = ROOT / "ml"

ZONE_RADIUS_NM = 10
DEFAULT_WAV = "ml/demo_upcall.wav"
SIM_RESPONSE_SECONDS = 4.0

# Simulated-time acceleration: 1 real second = TIME_SCALE simulated seconds
# (TIME_SCALE = 60 -> 1 real second is 1 simulated minute). Configurable.
TIME_SCALE = 60.0

# Each ship ping-pongs back and forth along its heading line, never straying
# more than MAX_OFFSET_NM from its seed position (keeps the demo stable).
MAX_OFFSET_NM = 1.5

# 1 nautical mile = 1/60 degree of latitude.
NM_PER_DEGREE_LAT = 60.0

# Status values.
NORMAL = "normal"
ALERTED = "alerted"
COMPLYING = "complying"
NOT_COMPLYING = "not_complying"


@dataclass(frozen=True)
class VesselSeed:
    id: str
    name: str
    type: str
    lat: float
    lon: float
    heading: int
    speed: int  # starting speed, knots


# Nine vessels. Most sit along a Boston shipping lane running roughly east from
# Boston Harbor (~42.33N, -70.90W). Coordinates chosen so that exactly the four
# cluster vessels fall within 10 nm of H-2 (see HYDROPHONES / test).
VESSEL_SEEDS: list[VesselSeed] = [
    VesselSeed("V-1", "Mystic", "tug", 42.37, -71.00, 90, 9),
    VesselSeed("V-2", "Atlantic Star", "container", 42.26, -70.38, 90, 18),
    VesselSeed("V-3", "Orion Bay", "bulk", 42.24, -70.34, 85, 17),
    VesselSeed("V-4", "Blue Fin II", "fishing", 42.34, -70.70, 95, 11),
    VesselSeed("V-5", "Nordic Tide", "tanker", 42.36, -70.66, 90, 16),
    VesselSeed("V-6", "Harbor Queen", "ferry", 42.31, -70.69, 100, 22),
    VesselSeed("V-7", "Cape Runner", "container", 42.33, -70.60, 90, 19),
    VesselSeed("V-8", "Sea Ledger", "research", 42.56, -70.66, 10, 15),
    VesselSeed("V-9", "Gull Point", "sailboat", 42.09, -70.70, 170, 8),
]

# Four hydrophones. H-2 is the demo detection site.
HYDROPHONES: dict[str, tuple[float, float]] = {
    "H-1": (42.345, -70.930),
    "H-2": (42.335, -70.665),
    "H-3": (42.300, -70.520),
    "H-4": (42.270, -70.400),
}

# Response after SIM_RESPONSE_SECONDS, keyed by vessel name: (after_speed, status).
RESPONSE_MAP: dict[str, tuple[int, str]] = {
    "Nordic Tide": (10, COMPLYING),
    "Harbor Queen": (10, COMPLYING),
    "Blue Fin II": (9, COMPLYING),
    "Cape Runner": (17, NOT_COMPLYING),
}


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points, in nautical miles."""
    r_km = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    km = 2 * r_km * math.asin(math.sqrt(a))
    return km / 1.852


def _pingpong(distance_nm: float, span_nm: float = MAX_OFFSET_NM) -> tuple[float, bool]:
    """Fold a monotonically increasing travelled distance into a ping-pong.

    Returns (offset_nm, reversed) where offset_nm is in [0, span_nm] measured
    from the seed position along the heading line, and `reversed` is True while
    the ship is travelling back toward the seed (heading flipped 180 deg).
    """
    if span_nm <= 0:
        return 0.0, False
    period = 2.0 * span_nm
    m = distance_nm % period
    if m <= span_nm:
        return m, False
    return period - m, True


def _offset_latlon(
    lat: float, lon: float, heading_deg: float, offset_nm: float
) -> tuple[float, float]:
    """Point reached by travelling `offset_nm` from (lat, lon) along heading.

    Uses a local flat-earth approximation (fine for <= a few nm). Heading is
    compass degrees: 0 = north, 90 = east.
    """
    theta = math.radians(heading_deg)
    north_nm = offset_nm * math.cos(theta)
    east_nm = offset_nm * math.sin(theta)
    dlat = north_nm / NM_PER_DEGREE_LAT
    cos_lat = math.cos(math.radians(lat))
    dlon = east_nm / (NM_PER_DEGREE_LAT * cos_lat) if cos_lat else 0.0
    return lat + dlat, lon + dlon


def resolve_wav(wav: str | None) -> Path:
    """Resolve a requested wav path, allowing only paths inside ml/."""
    rel = wav or DEFAULT_WAV
    candidate = (ROOT / rel).resolve()
    ml_root = ML_DIR.resolve()
    if ml_root not in candidate.parents and candidate != ml_root:
        raise ValueError(f"wav must be inside ml/: {rel}")
    return candidate


class Simulation:
    """Mutable simulation state with an injectable clock."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self.clock = clock
        self.reset()

    # --- lifecycle ---------------------------------------------------------

    def reset(self) -> None:
        """Restore seed positions, the clock baseline, detections, and stats."""
        self._baseline = self.clock()
        self._vessels: dict[str, dict[str, Any]] = {}
        for s in VESSEL_SEEDS:
            self._vessels[s.id] = {
                "id": s.id,
                "name": s.name,
                "type": s.type,
                # Seed (home) position + heading are immutable references used
                # to integrate ping-pong movement; current position is derived.
                "seed_lat": s.lat,
                "seed_lon": s.lon,
                "seed_heading": s.heading,
                "seed_speed": s.speed,
                "speed": s.speed,
                "status": NORMAL,
                # Simulated-seconds offset (from baseline) at which this
                # vessel's speed last changed, and the distance already
                # travelled up to that moment. None => speed never changed.
                "speed_change_sim_s": None,
                "distance_before_change_nm": 0.0,
            }
        self._detection: dict[str, Any] | None = None
        self._detection_time: float | None = None
        self._responded: bool = False
        self._stats = {"detections": 0, "alerts_sent": 0}

    # --- movement ----------------------------------------------------------

    def _sim_seconds(self) -> float:
        """Simulated seconds elapsed since the clock baseline."""
        return max(0.0, (self.clock() - self._baseline) * TIME_SCALE)

    def _travelled_nm(self, v: dict[str, Any], sim_s: float | None = None) -> float:
        """Piecewise cumulative distance (nm) travelled by vessel `v`.

        Before a speed change the vessel moves at its seed speed; after a
        change (recorded by _apply_response_if_due) it moves at the new speed,
        so a slowdown takes effect from that instant.
        """
        if sim_s is None:
            sim_s = self._sim_seconds()
        change_s = v["speed_change_sim_s"]
        if change_s is None or sim_s <= change_s:
            return v["seed_speed"] * sim_s / 3600.0
        # Distance up to the change, then at the current speed afterward.
        return v["distance_before_change_nm"] + v["speed"] * (sim_s - change_s) / 3600.0

    def _position(self, v: dict[str, Any], sim_s: float | None = None) -> tuple[float, float, float]:
        """Current (lat, lon, heading) for vessel `v` at the given sim time.

        Heading is flipped 180 deg while the ship travels back toward its seed.
        """
        travelled = self._travelled_nm(v, sim_s)
        offset, reversed_ = _pingpong(travelled)
        heading = v["seed_heading"]
        if reversed_:
            heading = (heading + 180) % 360
        lat, lon = _offset_latlon(v["seed_lat"], v["seed_lon"], v["seed_heading"], offset)
        return lat, lon, heading

    # --- internal helpers --------------------------------------------------

    def _response_due(self) -> bool:
        if self._detection is None or self._detection_time is None:
            return False
        return (self.clock() - self._detection_time) >= SIM_RESPONSE_SECONDS

    def _apply_response_if_due(self) -> None:
        """Lazily advance alerted vessels to their response once time passes."""
        if self._responded or not self._response_due():
            return
        # The change happens exactly at the response threshold, not "now", so
        # the piecewise distance integral is continuous and observer-agnostic.
        change_sim_s = max(
            0.0, (self._detection_time + SIM_RESPONSE_SECONDS - self._baseline) * TIME_SCALE
        )
        for v in self._vessels.values():
            if v["status"] == ALERTED and v["name"] in RESPONSE_MAP:
                after, status = RESPONSE_MAP[v["name"]]
                # Freeze distance travelled up to the change, then switch speed.
                v["distance_before_change_nm"] = self._travelled_nm(v, change_sim_s)
                v["speed_change_sim_s"] = change_sim_s
                v["speed"] = after
                v["status"] = status
        self._responded = True

    def _in_zone_ids(self) -> list[str]:
        if self._detection is None:
            return []
        return [x["id"] for x in self._detection["vessels_in_zone"]]

    # --- reads -------------------------------------------------------------

    def vessels(self) -> list[dict[str, Any]]:
        self._apply_response_if_due()
        out = []
        for v in self._vessels.values():
            lat, lon, heading = self._position(v)
            out.append(
                {
                    "id": v["id"],
                    "name": v["name"],
                    "type": v["type"],
                    "lat": lat,
                    "lon": lon,
                    "heading": heading,
                    "speed": v["speed"],
                    "status": v["status"],
                    "simulated": True,
                }
            )
        return out

    def compliance(self) -> dict[str, Any]:
        self._apply_response_if_due()
        if self._detection is None or not self._responded:
            return {"compliance_pct": None, "vessels": [], "simulated": True}

        rows = []
        complying = 0
        in_zone = self._in_zone_ids()
        for entry in self._detection["vessels_in_zone"]:
            v = self._vessels[entry["id"]]
            if v["status"] == COMPLYING:
                complying += 1
            rows.append(
                {
                    "id": v["id"],
                    "name": v["name"],
                    "before": entry["speed_before"],
                    "after": v["speed"],
                    "status": v["status"],
                }
            )
        pct = round(complying / len(in_zone) * 100, 1) if in_zone else None
        return {"compliance_pct": pct, "vessels": rows, "simulated": True}

    def stats(self) -> dict[str, Any]:
        comp = self.compliance()["compliance_pct"]
        return {
            "detections": self._stats["detections"],
            "alerts_sent": self._stats["alerts_sent"],
            "compliance_pct": comp,
            "simulated": True,
        }

    def has_active_detection(self) -> bool:
        """True if a detection is active (and not yet cleared by reset)."""
        return self._detection is not None

    def active_detection_id(self) -> str | None:
        """The current detection's id, or None if no detection is active."""
        return self._detection["detection_id"] if self._detection else None

    def brief_inputs(self) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Return (detection, compliance) in build_demo_input() shape from the
        current sim state, or None if no detection is active or the vessels have
        not responded yet (compliance_pct is still null).

        Read-only: computes the response if due, but reports the same state the
        read endpoints expose. Confidence/display and per-vessel before/after
        come straight from the live detection and compliance.
        """
        self._apply_response_if_due()
        comp = self.compliance()
        if self._detection is None or comp["compliance_pct"] is None:
            return None

        det = self._detection
        detection = {
            "detection_id": det["detection_id"],
            "hydrophone_id": det["hydrophone_id"],
            "confidence": det["confidence"],
            "confidence_display": f"{float(det['confidence']):.2f}",
            "zone": dict(det["zone"]),
            "vessels_in_zone": [dict(v) for v in det["vessels_in_zone"]],
            "synthetic_demo_clip": True,
            "simulated": True,
        }
        pct = comp["compliance_pct"]
        compliance = {
            "compliance_pct": pct,
            "compliance_display": f"{pct:g}%",
            "vessels": [dict(v) for v in comp["vessels"]],
            "simulated": True,
        }
        return detection, compliance

    # --- writes ------------------------------------------------------------

    def create_detection(self, hydrophone_id: str, confidence: float) -> dict[str, Any]:
        """Create a 10 nm zone at the hydrophone and alert in-zone vessels.

        `confidence` is supplied by the caller (from ml.predict); it is never
        computed here.
        """
        if hydrophone_id not in HYDROPHONES:
            raise KeyError(f"unknown hydrophone: {hydrophone_id}")
        hlat, hlon = HYDROPHONES[hydrophone_id]

        # Reset any prior detection's alert state so counts stay consistent.
        for v in self._vessels.values():
            if v["status"] == ALERTED:
                v["status"] = NORMAL
        self._responded = False

        in_zone = []
        for v in self._vessels.values():
            vlat, vlon, _heading = self._position(v)
            if haversine_nm(hlat, hlon, vlat, vlon) <= ZONE_RADIUS_NM:
                v["status"] = ALERTED
                in_zone.append({"id": v["id"], "name": v["name"], "speed_before": v["speed"]})

        detection = {
            "detection_id": f"DET-{self._stats['detections'] + 1}",
            "hydrophone_id": hydrophone_id,
            "confidence": confidence,
            "zone": {"lat": hlat, "lon": hlon, "radius_nm": ZONE_RADIUS_NM},
            "vessels_in_zone": in_zone,
            "synthetic_demo_clip": True,
            "simulated": True,
        }
        self._detection = detection
        self._detection_time = self.clock()
        self._stats["detections"] += 1
        self._stats["alerts_sent"] += len(in_zone)
        return detection

    def hydrophones(self) -> list[dict[str, Any]]:
        """Return the 4 defined hydrophones (positions unchanged)."""
        return [
            {"id": hid, "lat": lat, "lon": lon, "simulated": True}
            for hid, (lat, lon) in HYDROPHONES.items()
        ]

    def brief_default_path(self) -> Path:
        return ROOT / "backend" / "cache" / "brief.json"
