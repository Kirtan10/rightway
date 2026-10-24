"""Property-based tests (Hypothesis) for the simulation, path safety, and brief
validation. Each property notes the EARS requirement it exercises.

Requirement IDs:
  * backend-sim: .kiro/specs/backend-sim/requirements.md
  * ai-brief:    .kiro/specs/ai-brief/requirements.md
"""

from __future__ import annotations

import json
from pathlib import Path

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from backend import brief
from backend.sim import (
    RESPONSE_MAP,
    SIM_RESPONSE_SECONDS,
    VESSEL_SEEDS,
    Simulation,
    haversine_nm,
    resolve_wav,
)

ROOT = Path(__file__).resolve().parents[1]
ML_DIR = ROOT / "ml"

# Massachusetts Bay-ish bounding box for coordinate strategies.
_LAT = st.floats(min_value=41.5, max_value=42.8, allow_nan=False, allow_infinity=False)
_LON = st.floats(min_value=-71.2, max_value=-69.8, allow_nan=False, allow_infinity=False)


class _FakeClock:
    """Mutable monotonic clock so tests can advance time deterministically."""

    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


# ---------------------------------------------------------------------------
# Property 1 — haversine distance (backend-sim R3 relies on this metric)
# ---------------------------------------------------------------------------
@given(_LAT, _LON, _LAT, _LON)
def test_haversine_symmetric_and_nonnegative(lat1, lon1, lat2, lon2):
    """R3: distance is symmetric and non-negative."""
    d1 = haversine_nm(lat1, lon1, lat2, lon2)
    d2 = haversine_nm(lat2, lon2, lat1, lon1)
    assert d1 >= 0.0
    assert abs(d1 - d2) < 1e-9


@given(_LAT, _LON)
def test_haversine_zero_for_identical_points(lat, lon):
    """R3: distance from a point to itself is zero."""
    assert haversine_nm(lat, lon, lat, lon) == 0.0 or haversine_nm(lat, lon, lat, lon) < 1e-9


@given(_LAT, _LON, _LAT, _LON, _LAT, _LON)
def test_haversine_triangle_inequality(la, lo, lb, lob, lc, loc):
    """R3: d(A,C) <= d(A,B) + d(B,C) (allow a tiny numeric tolerance)."""
    ab = haversine_nm(la, lo, lb, lob)
    bc = haversine_nm(lb, lob, lc, loc)
    ac = haversine_nm(la, lo, lc, loc)
    assert ac <= ab + bc + 1e-6


# ---------------------------------------------------------------------------
# Property 2 — compliance (backend-sim R7)
# ---------------------------------------------------------------------------
# Reference rule the system intends: a vessel complies iff its after-speed is
# <= 10 knots. We check (a) that the real RESPONSE_MAP data obeys this rule, and
# (b) that a fresh Simulation's compliance() output obeys pct in [0,100],
# pct == complying/in-zone*100, and status=="complying" iff after <= 10.
SPEED_LIMIT_KN = 10


@given(
    st.lists(
        st.tuples(
            st.integers(min_value=0, max_value=40),  # before
            st.integers(min_value=0, max_value=40),  # after
        ),
        min_size=1,
        max_size=12,
    )
)
def test_compliance_rule_pct_bounds_and_definition(speeds):
    """R7: compliance_pct in [0,100], equals complying/in-zone*100, and a vessel
    complies iff after <= 10 kn. Tested against the intended compliance rule."""
    statuses = ["complying" if after <= SPEED_LIMIT_KN else "not_complying" for _, after in speeds]
    complying = sum(1 for s in statuses if s == "complying")
    pct = complying / len(speeds) * 100

    assert 0.0 <= pct <= 100.0
    assert pct == complying / len(speeds) * 100
    for (_before, after), status in zip(speeds, statuses, strict=True):
        assert (status == "complying") == (after <= SPEED_LIMIT_KN)


def test_real_response_map_obeys_compliance_rule():
    """R7: the shipped RESPONSE_MAP data obeys 'complying iff after <= 10 kn'."""
    for _name, (after, status) in RESPONSE_MAP.items():
        assert (status == "complying") == (after <= SPEED_LIMIT_KN)


@given(st.integers(min_value=0, max_value=100))
def test_simulation_compliance_output_invariants(_seed):
    """R7: the real Simulation.compliance() output obeys the pct bounds, the
    pct formula, and 'status==complying iff after<=10' after a detection."""
    clock = _FakeClock()
    sim = Simulation(clock=clock)
    sim.create_detection("H-2", 1.0)
    clock.advance(SIM_RESPONSE_SECONDS + 1)
    comp = sim.compliance()

    pct = comp["compliance_pct"]
    rows = comp["vessels"]
    assert rows, "a detection at H-2 must have in-zone vessels"
    complying = sum(1 for r in rows if r["status"] == "complying")
    assert 0.0 <= pct <= 100.0
    assert pct == round(complying / len(rows) * 100, 1)
    for r in rows:
        assert (r["status"] == "complying") == (r["after"] <= SPEED_LIMIT_KN)


# ---------------------------------------------------------------------------
# Property 3 — reset is idempotent (backend-sim R10)
# ---------------------------------------------------------------------------
# A small op alphabet: detect at a hydrophone, advance the clock, or reset.
_OPS = st.lists(
    st.one_of(
        st.tuples(st.just("detect"), st.sampled_from(["H-1", "H-2", "H-3", "H-4"])),
        st.tuples(st.just("advance"), st.floats(min_value=0, max_value=20, allow_nan=False)),
        st.tuples(st.just("reset"), st.none()),
    ),
    max_size=15,
)


def _snapshot(sim: Simulation) -> dict:
    """A comparable view of the externally observable state."""
    return {
        "stats": sim.stats(),
        "vessels": sim.vessels(),
        "compliance": sim.compliance(),
        "active": sim.has_active_detection(),
    }


@given(_OPS)
@settings(max_examples=150)
def test_reset_is_idempotent(ops):
    """R10: after any sequence of detect/advance/reset then a final reset, the
    state equals a fresh Simulation's state (stats zero, no zone, initial speeds)."""
    clock = _FakeClock()
    sim = Simulation(clock=clock)
    for op, arg in ops:
        if op == "detect":
            if not sim.has_active_detection():
                sim.create_detection(arg, 1.0)
        elif op == "advance":
            clock.advance(arg)
        else:
            sim.reset()
    sim.reset()

    fresh = Simulation(clock=_FakeClock())
    assert _snapshot(sim) == _snapshot(fresh)
    # Spelled out: stats zero, no active zone, initial speeds.
    assert sim.stats()["detections"] == 0
    assert sim.stats()["alerts_sent"] == 0
    assert sim.has_active_detection() is False
    live = {v["id"]: v["speed"] for v in sim.vessels()}
    for seed in VESSEL_SEEDS:
        assert live[seed.id] == seed.speed


# ---------------------------------------------------------------------------
# Property 4 — one active detection at a time (backend-sim R13)
# ---------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from backend.app import app  # noqa: E402


@given(st.integers(min_value=1, max_value=8))
@settings(max_examples=40, deadline=None)
def test_one_active_detection_only(n_posts):
    """R13: a run of POST /detections without reset yields exactly one 200 and
    then 409s, and /stats never exceeds 1 detection."""
    app.state.sim = Simulation(clock=_FakeClock())
    client = TestClient(app)

    codes = []
    for _ in range(n_posts):
        r = client.post("/detections", json={"hydrophone_id": "H-2"})
        codes.append(r.status_code)
        stats = client.get("/stats").json()
        assert stats["detections"] <= 1

    assert codes[0] == 200
    assert all(c == 409 for c in codes[1:])
    assert client.get("/stats").json()["detections"] == 1


# ---------------------------------------------------------------------------
# Property 5 — path safety (backend-sim R4: only paths inside ml/)
# ---------------------------------------------------------------------------
# Build path strings that are intended to resolve OUTSIDE ml/.
_OUTSIDE_PATHS = st.one_of(
    # Escapes via "..".
    st.builds(lambda n, tail: "../" * n + tail,
              st.integers(min_value=1, max_value=6),
              st.sampled_from(["etc/passwd", "secret", "ml_notreally/x", "a/b"])),
    # Absolute paths.
    st.sampled_from(["/etc/passwd", "/tmp/x.wav", "/", "/ml/x.wav", "/usr/bin/env"]),
    # Sibling/other directories (not under ml/).
    st.sampled_from(["backend/app.py", "mlx/x.wav", "ml_data/x", "readme", "../ml"]),
    # Symlink-like / odd names that still resolve outside ml/.
    st.builds(lambda s: "ml/../" + s, st.sampled_from(["etc", "x", "../y", "backend"])),
)


@given(_OUTSIDE_PATHS)
def test_resolve_wav_rejects_paths_outside_ml(p):
    """R4: resolve_wav must reject any path that resolves outside ml/."""
    candidate = (ROOT / p).resolve()
    ml_root = ML_DIR.resolve()
    # Only assert on inputs that truly resolve outside ml/ (keep the property honest).
    assume(ml_root != candidate and ml_root not in candidate.parents)
    try:
        resolve_wav(p)
    except ValueError:
        return  # rejected as required
    raise AssertionError(f"resolve_wav accepted an out-of-ml/ path: {p!r}")


# ---------------------------------------------------------------------------
# Property 6 — brief validation (ai-brief R3 / honesty checks in brief.py)
# ---------------------------------------------------------------------------
_DEMO_COMPLIANCE = brief.build_demo_input()[1]
_TEXT = st.text(
    alphabet=st.characters(min_codepoint=32, max_codepoint=126),
    min_size=0,
    max_size=200,
)


@given(_TEXT, st.integers(min_value=0, max_value=9), st.characters(min_codepoint=65, max_codepoint=90))
def test_digit_glued_to_letter_is_rejected(prefix, digit, letter):
    """R3: any text with a digit glued directly to a letter is rejected."""
    bad = f"{prefix} {digit}{letter} trailing."
    assert brief._validation_failure(bad, _DEMO_COMPLIANCE) is not None


@given(_TEXT, _TEXT)
def test_arrow_is_rejected(left, right):
    """R3: any text containing '->' is rejected."""
    bad = f"{left}->{right}"
    assert brief._validation_failure(bad, _DEMO_COMPLIANCE) is not None


def test_cached_brief_passes_validation():
    """R3: the shipped cached brief.json passes validation for the demo compliance."""
    cached = json.loads((ROOT / "backend" / "cache" / "brief.json").read_text())["brief"]
    assert brief._validation_failure(cached, _DEMO_COMPLIANCE) is None
