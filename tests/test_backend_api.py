"""API tests for the backend-sim feature (FastAPI TestClient, injected clock)."""

from __future__ import annotations

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
    # Replace the module-level simulation with one on the injected clock.
    app.state.sim = Simulation(clock=clock)
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
    assert body["source"] == "cache"
    assert "brief" in body


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
