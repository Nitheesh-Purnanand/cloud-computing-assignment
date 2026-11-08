import importlib

import pytest
from fastapi.testclient import TestClient

GOOD = '{"intent": "weather_query", "date": null, "time": null, "place": "london"}'


@pytest.fixture
def make_client(monkeypatch):
    def _make(fault="0", output=GOOD, ready=True):
        monkeypatch.setenv("FAULT_INJECT", fault)
        monkeypatch.setenv("MODEL_VERSION", "vtest")
        import app
        app = importlib.reload(app)
        app.state["model"] = object() if ready else None
        monkeypatch.setattr(app, "generate", lambda text: output)
        return TestClient(app.app)  # no `with`: the startup download is not triggered
    return _make


def test_parse_ok_with_headers(make_client):
    r = make_client().post("/parse", json={"text": "what is the weather in london"})
    assert r.status_code == 200
    assert r.json() == {"intent": "weather_query", "date": None, "time": None, "place": "london"}
    assert r.headers["X-Model-Version"] == "vtest" and r.headers["X-Served-By"]


def test_fault_inject_returns_500(make_client):
    r = make_client(fault="1").post("/parse", json={"text": "hi"})
    assert r.status_code == 500 and r.json() == {"error": "invalid_model_output"}


def test_schema_violation_returns_500(make_client):
    bad = '{"intent": "dance", "date": null, "time": null, "place": null}'
    r = make_client(output=bad).post("/parse", json={"text": "hi"})
    assert r.status_code == 500 and r.json() == {"error": "invalid_model_output"}


def test_probes(make_client):
    c = make_client(ready=False)
    assert c.get("/healthz").status_code == 200
    assert c.get("/readyz").status_code == 503
    assert make_client().get("/readyz").status_code == 200
