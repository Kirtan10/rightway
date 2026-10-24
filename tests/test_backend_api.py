"""API tests for the backend-sim feature (FastAPI TestClient, injected clock)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from backend import app as app_module
from backend import sim as sim_module
from backend.app import app
from backend.sim import HYDROPHONES, VESSEL_SEEDS, Simulation, haversine_nm


class FakeClock:
    """Mutable monotonic clock for deterministic time advancement."""

    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def client(clock: FakeClock) -> TestClient:
    # Replace the module-level simulation with one on the injected clock, and
    # clear the per-detection brief cache so tests don't bleed into each other.
    app.state.sim = Simulation(clock=clock)
    app.state.brief_cache = {}
    return TestClient(app)


TARGETS = {"Nordic Tide", "Harbor Queen", "Blue Fin II", "Cape Runner"}


def test_h2_zone_membership_by_haversine():
    hlat, hlon = HYDROPHONES["H-2"]
    inside = set()
    for s in VESSEL_SEEDS:
        if haversine_nm(hlat, hlon, s.lat, s.lon) <= 10:
            inside.add(s.name)
    assert inside == TARGETS


def test_hydrophones_endpoint(client: TestClient):
    r = client.get("/hydrophones")
    assert r.status_code == 200
    body = r.json()
    assert {h["id"] for h in body} == {"H-1", "H-2", "H-3", "H-4"}
    for h in body:
        assert set(h) == {"id", "lat", "lon", "simulated"}
        assert h["simulated"] is True

    # H-2 must match the /detections zone center.
    h2 = next(h for h in body if h["id"] == "H-2")
    det = client.post("/detections", json={"hydrophone_id": "H-2"}).json()
    assert det["zone"]["lat"] == h2["lat"]
    assert det["zone"]["lon"] == h2["lon"]


def test_detection_response_shape_and_flags(client: TestClient):
    r = client.post("/detections", json={"hydrophone_id": "H-2"})
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {
        "detection_id",
        "hydrophone_id",
        "confidence",
        "zone",
        "vessels_in_zone",
        "synthetic_demo_clip",
        "simulated",
    }
    assert body["hydrophone_id"] == "H-2"
    assert body["zone"]["radius_nm"] == 10
    assert body["synthetic_demo_clip"] is True
    assert body["simulated"] is True
    assert 0.0 <= body["confidence"] <= 1.0
    names = {v["name"] for v in body["vessels_in_zone"]}
    assert names == TARGETS
    for v in body["vessels_in_zone"]:
        assert set(v) == {"id", "name", "speed_before"}


def test_second_detection_without_reset_returns_409(client: TestClient):
    first = client.post("/detections", json={"hydrophone_id": "H-2"})
    assert first.status_code == 200

    second = client.post("/detections", json={"hydrophone_id": "H-2"})
    assert second.status_code == 409
    assert second.json()["detail"] == "A detection is already active. Reset first."

    # The second POST changed nothing: still 1 detection and 4 alerts.
    stats = client.get("/stats").json()
    assert stats["detections"] == 1
    assert stats["alerts_sent"] == 4


def test_response_after_delay_and_75pct_compliance(client: TestClient, clock: FakeClock):
    client.post("/detections", json={"hydrophone_id": "H-2"})

    # Before the delay: vessels still alerted, compliance is null.
    assert client.get("/compliance").json()["compliance_pct"] is None
    alerted = {v["name"]: v for v in client.get("/vessels").json() if v["status"] == "alerted"}
    assert set(alerted) == TARGETS

    # Advance past the response window (no sleep).
    clock.advance(sim_module.SIM_RESPONSE_SECONDS + 0.1)

    comp = client.get("/compliance").json()
    assert comp["compliance_pct"] == 75.0
    assert comp["simulated"] is True
    by_name = {row["name"]: row for row in comp["vessels"]}
    assert by_name["Nordic Tide"]["before"] == 16 and by_name["Nordic Tide"]["after"] == 10
    assert by_name["Harbor Queen"]["before"] == 22 and by_name["Harbor Queen"]["after"] == 10
    assert by_name["Blue Fin II"]["before"] == 11 and by_name["Blue Fin II"]["after"] == 9
    assert by_name["Cape Runner"]["after"] == 17
    assert by_name["Cape Runner"]["status"] == "not_complying"


def test_stats_increment_and_reset(client: TestClient, clock: FakeClock):
    start = client.get("/stats").json()
    assert start["detections"] == 0 and start["alerts_sent"] == 0

    client.post("/detections", json={"hydrophone_id": "H-2"})
    clock.advance(sim_module.SIM_RESPONSE_SECONDS + 0.1)
    s = client.get("/stats").json()
    assert s["detections"] == 1
    assert s["alerts_sent"] == 4
    assert s["compliance_pct"] == 75.0
    assert s["simulated"] is True

    assert client.post("/reset").json()["ok"] is True
    z = client.get("/stats").json()
    assert z["detections"] == 0 and z["alerts_sent"] == 0 and z["compliance_pct"] is None
    assert all(v["status"] == "normal" for v in client.get("/vessels").json())


def test_brief_default_source(client: TestClient):
    body = client.get("/brief").json()
    assert body["source"] in {"cache", "bedrock"}
    assert "simulated" in body["brief"].lower()
    assert "brief" in body


def test_brief_before_detection_returns_cached_file(client: TestClient, monkeypatch):
    calls = []
    monkeypatch.setattr(
        app_module.brief_module,
        "generate_brief_result",
        lambda d, c: calls.append((d, c)) or {"brief": "x", "source": "bedrock"},
    )
    body = client.get("/brief").json()
    # Before a detection the cached file is returned as-is (no live generation,
    # no per-detection fields). Its source is whatever the file contains.
    assert calls == []  # no live brief before a detection
    assert "detection_id" not in body
    assert "generated_at" not in body
    cached = json.loads((app_module._sim().brief_default_path()).read_text())
    cached.setdefault("source", "cache")
    assert body == cached


def test_brief_live_after_response_generated_once(
    client: TestClient, clock: FakeClock, monkeypatch
):
    calls = []

    def fake_generate(detection, _compliance):
        calls.append(detection["detection_id"])
        return {"brief": "LIVE right whale up-call 10 nm simulated 75%", "source": "bedrock"}

    monkeypatch.setattr(app_module.brief_module, "generate_brief_result", fake_generate)

    client.post("/detections", json={"hydrophone_id": "H-2"})
    clock.advance(sim_module.SIM_RESPONSE_SECONDS + 1)

    first = client.get("/brief").json()
    assert first["source"] == "bedrock"
    assert first["brief"] == "LIVE right whale up-call 10 nm simulated 75%"
    assert first["detection_id"] == "DET-1"
    assert "generated_at" in first
    assert calls == ["DET-1"]  # called once with the live detection_id

    # A second GET must reuse the cached result, not call again.
    second = client.get("/brief").json()
    assert second == first
    assert calls == ["DET-1"]
    assert client.get("/stats").json()["detections"] == 1


def test_brief_live_source_cache_returns_file(client: TestClient, clock: FakeClock, monkeypatch):
    monkeypatch.setattr(
        app_module.brief_module,
        "generate_brief_result",
        lambda d, c: {"brief": "ignored when source is cache", "source": "cache"},
    )
    client.post("/detections", json={"hydrophone_id": "H-2"})
    clock.advance(sim_module.SIM_RESPONSE_SECONDS + 1)
    body = client.get("/brief").json()
    assert body["source"] == "cache"
    # Body comes from backend/cache/brief.json, not the live (rejected) text.
    assert body["brief"] != "ignored when source is cache"
    assert body["detection_id"] == "DET-1"


def test_reset_clears_per_detection_brief_cache(
    client: TestClient, clock: FakeClock, monkeypatch
):
    calls = []

    def fake_generate(detection, _compliance):
        calls.append(detection["detection_id"])
        return {"brief": "LIVE right whale up-call 10 nm simulated 75%", "source": "bedrock"}

    monkeypatch.setattr(app_module.brief_module, "generate_brief_result", fake_generate)

    client.post("/detections", json={"hydrophone_id": "H-2"})
    clock.advance(sim_module.SIM_RESPONSE_SECONDS + 1)
    client.get("/brief")
    assert calls == ["DET-1"]

    client.post("/reset")
    assert app.state.brief_cache == {}  # cleared on reset

    # A fresh detection generates again. Reset zeroes the detection counter, so
    # the id is DET-1 again; because the cache was cleared, generate is called a
    # second time (a stale cache would have been a hit and skipped the call).
    client.post("/detections", json={"hydrophone_id": "H-2"})
    clock.advance(sim_module.SIM_RESPONSE_SECONDS + 1)
    client.get("/brief")
    assert calls == ["DET-1", "DET-1"]


def test_detection_returns_503_when_predict_raises(client: TestClient, monkeypatch):
    def boom(_wav):
        raise RuntimeError("model missing")

    # Patch where the route imports it from (ml.predict.predict).
    monkeypatch.setattr("ml.predict.predict", boom)
    r = client.post("/detections", json={"hydrophone_id": "H-2"})
    assert r.status_code == 503
    assert "model missing" in r.json()["detail"]


def test_static_allows_only_the_four_assets(client: TestClient):
    ok = client.get("/static/demo_upcall.wav")
    assert ok.status_code == 200

    bad = client.get("/static/secret.txt")
    assert bad.status_code == 404

    traversal = client.get("/static/..%2Fmetrics.json")
    assert traversal.status_code == 404


def test_app_module_has_singleton_sim():
    # Sanity: the module exposes a Simulation instance for uvicorn.
    assert isinstance(app_module.app.state.sim, Simulation)
