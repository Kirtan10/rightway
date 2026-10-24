"""Movement tests for backend.sim: ping-pong motion and zone stability.

All vessel data is simulated. These tests use an injectable clock so time is
deterministic and no real sleeping occurs.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from backend.sim import (
    HYDROPHONES,
    MAX_OFFSET_NM,
    SIM_RESPONSE_SECONDS,
    VESSEL_SEEDS,
    Simulation,
    haversine_nm,
)

TARGETS = {"Blue Fin II", "Nordic Tide", "Harbor Queen", "Cape Runner"}

# Haversine vs. the flat-earth movement model differ by < 0.002 nm at 1.5 nm;
# allow a small tolerance when asserting the wander bound.
OFFSET_TOL_NM = 0.01

_SEED_LATLON = {s.name: (s.lat, s.lon) for s in VESSEL_SEEDS}


class ManualClock:
    """Settable clock for deterministic simulated time."""

    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def set(self, t: float) -> None:
        self.t = t


@given(
    # Real seconds elapsed since baseline, and real seconds from baseline to the
    # detection (both bounded but large enough to exercise many ping-pong laps).
    elapsed=st.floats(min_value=0.0, max_value=5_000.0),
    detect_at=st.floats(min_value=0.0, max_value=5_000.0),
)
@settings(max_examples=250, deadline=None)
def test_zone_membership_and_wander_invariant(elapsed: float, detect_at: float):
    base = 1000.0
    clock = ManualClock(base)
    sim = Simulation(clock=clock)

    # Fire a detection at an arbitrary time, then let more time pass.
    clock.set(base + detect_at)
    sim.create_detection("H-2", 0.9)
    # Advance past the response threshold sometimes, to vary speeds too.
    clock.set(base + detect_at + elapsed)

    hlat, hlon = HYDROPHONES["H-2"]
    vessels = {v["name"]: v for v in sim.vessels()}

    inside = {
        name
        for name, v in vessels.items()
        if haversine_nm(hlat, hlon, v["lat"], v["lon"]) <= 10.0
    }
    assert inside == TARGETS

    for name, v in vessels.items():
        slat, slon = _SEED_LATLON[name]
        assert haversine_nm(slat, slon, v["lat"], v["lon"]) <= MAX_OFFSET_NM + OFFSET_TOL_NM


def test_position_changes_as_clock_advances():
    clock = ManualClock(0.0)
    sim = Simulation(clock=clock)
    before = {v["name"]: (v["lat"], v["lon"]) for v in sim.vessels()}

    clock.set(5.0)  # 5 real s -> 300 simulated s of motion
    after = {v["name"]: (v["lat"], v["lon"]) for v in sim.vessels()}

    moved = [n for n in before if before[n] != after[n]]
    # Every moving ship (all have positive speed) should have shifted.
    assert len(moved) == len(before)


def test_slowed_ship_covers_less_distance_after_response():
    clock = ManualClock(0.0)
    sim = Simulation(clock=clock)

    sim.create_detection("H-2", 0.9)
    # Observe the response (Nordic Tide 16 -> 10 kn) by reading after the delay.
    clock.set(SIM_RESPONSE_SECONDS + 10.0)
    assert next(v for v in sim.vessels() if v["name"] == "Nordic Tide")["speed"] == 10

    v = sim._vessels["V-5"]  # Nordic Tide

    # Cumulative distance is monotonic, so distance over equal simulated-minute
    # windows isolates the speed. Compare a window before the change to one
    # after it. One simulated minute == 60 simulated seconds.
    change_s = v["speed_change_sim_s"]
    assert change_s is not None

    before = sim._travelled_nm(v, change_s) - sim._travelled_nm(v, change_s - 60.0)
    after = sim._travelled_nm(v, change_s + 60.0) - sim._travelled_nm(v, change_s)

    # 16 knots vs 10 knots over one simulated minute (knots = nm/hour).
    assert after < before
    assert before == pytest.approx(16.0 / 60.0)
    assert after == pytest.approx(10.0 / 60.0)


def test_cape_runner_stays_fast_after_response():
    clock = ManualClock(0.0)
    sim = Simulation(clock=clock)
    sim.create_detection("H-2", 0.9)
    clock.set(SIM_RESPONSE_SECONDS + 10.0)
    cape = next(v for v in sim.vessels() if v["name"] == "Cape Runner")
    # Cape Runner is the non-complier: it only eases 19 -> 17 and stays fast.
    assert cape["speed"] == 17
    assert cape["status"] == "not_complying"


def test_reset_restores_seed_positions():
    clock = ManualClock(0.0)
    sim = Simulation(clock=clock)

    clock.set(123.0)  # drift away from seed
    drifted = {v["name"]: (v["lat"], v["lon"]) for v in sim.vessels()}
    assert any(
        (lat, lon) != _SEED_LATLON[name] for name, (lat, lon) in drifted.items()
    )

    sim.reset()
    restored = {v["name"]: (v["lat"], v["lon"]) for v in sim.vessels()}
    for name, (lat, lon) in restored.items():
        assert (lat, lon) == _SEED_LATLON[name]
