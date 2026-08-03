"""Analyze progress tracker used by the UI progress overlay."""

from __future__ import annotations


def test_progress_stages_advance_and_eta():
    from backend.app.core import analyze_progress as ap

    ap.clear("prog-ds")
    ap.start("prog-ds", 10)
    tokens = ap.bind("prog-ds", 10)
    try:
        ap.report(stage="parse", message="Parsing a.csv", done=5, total=10)
        job = ap.get("prog-ds", 10)
        assert job is not None
        assert job["status"] == "running"
        assert job["done"] == 5 and job["total"] == 10
        assert 0 < job["percent"] < 55
        assert job["eta_seconds"] is not None

        ap.report(stage="detect", message="Scoring…", fraction=0.5)
        job = ap.get("prog-ds", 10)
        assert job["stage"] == "detect"
        assert job["percent"] > 55
    finally:
        ap.unbind(tokens)
        ap.finish("prog-ds", 10)
        done = ap.get("prog-ds", 10)
        assert done["status"] == "done"
        assert done["percent"] == 100


def test_progress_endpoint_idle_and_running(monkeypatch):
    import os

    os.environ["ERAKSHAK_JWT_SECRET"] = "test-secret"
    os.environ["ERAKSHAK_ADMIN_PASSWORD"] = "adminpass"

    from fastapi.testclient import TestClient

    from backend.app.api.main import app
    from backend.app.core import analyze_progress as ap

    with TestClient(app) as client:
        tok = client.post(
            "/v1/auth/token", data={"username": "admin", "password": "adminpass"}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {tok}"}

        idle = client.get("/v1/analyze/progress/nope?window=10", headers=headers)
        assert idle.status_code == 200
        assert idle.json()["status"] == "idle"

        ap.start("demo", 10)
        running = client.get("/v1/analyze/progress/demo?window=10", headers=headers)
        assert running.status_code == 200
        body = running.json()
        assert body["status"] == "running"
        assert "stages" in body
        ap.finish("demo", 10)
