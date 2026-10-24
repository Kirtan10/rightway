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
        """Restore initial vessel state, clear detections, zero stats."""
        self._vessels: dict[str, dict[str, Any]] = {}
        for s in VESSEL_SEEDS:
            self._vessels[s.id] = {
                "id": s.id,
                "name": s.name,
                "type": s.type,
                "lat": s.lat,
                "lon": s.lon,
                "heading": s.heading,
                "speed": s.speed,
                "status": NORMAL,
            }
        self._detection: dict[str, Any] | None = None
        self._detection_time: float | None = None
        self._responded: bool = False
        self._stats = {"detections": 0, "alerts_sent": 0}

    # --- internal helpers --------------------------------------------------

    def _response_due(self) -> bool:
        if self._detection is None or self._detection_time is None:
            return False
        return (self.clock() - self._detection_time) >= SIM_RESPONSE_SECONDS

    def _apply_response_if_due(self) -> None:
        """Lazily advance alerted vessels to their response once time passes."""
        if self._responded or not self._response_due():
            return
        for v in self._vessels.values():
            if v["status"] == ALERTED and v["name"] in RESPONSE_MAP:
                after, status = RESPONSE_MAP[v["name"]]
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
        return [
            {
                "id": v["id"],
                "name": v["name"],
                "type": v["type"],
                "lat": v["lat"],
                "lon": v["lon"],
                "heading": v["heading"],
                "speed": v["speed"],
                "status": v["status"],
                "simulated": True,
            }
            for v in self._vessels.values()
        ]

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
            if haversine_nm(hlat, hlon, v["lat"], v["lon"]) <= ZONE_RADIUS_NM:
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
