"""API auth/RBAC (C2) + persistence durability (C1) integration tests."""

import os

import pytest


@pytest.fixture(scope="module")
def client(monkeypatch_module=None):
    os.environ["ERAKSHAK_JWT_SECRET"] = "test-secret"
    os.environ["ERAKSHAK_ADMIN_PASSWORD"] = "adminpass"
    from fastapi.testclient import TestClient

    from backend.app.api.main import app
    return TestClient(app)


def test_health_is_public(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_protected_requires_auth(client):
    r = client.get("/v1/datasets")
    assert r.status_code == 401
    assert "error" in r.json()  # consistent error schema (M3)


def test_login_and_access(client):
    r = client.post("/v1/auth/token", data={"username": "admin", "password": "adminpass"})
    assert r.status_code == 200
    tok = r.json()["access_token"]
    r2 = client.get("/v1/datasets", headers={"Authorization": f"Bearer {tok}"})
    assert r2.status_code == 200
    assert "datasets" in r2.json()


def test_bad_login_rejected(client):
    r = client.post("/v1/auth/token", data={"username": "admin", "password": "nope"})
    assert r.status_code == 401


# ---- C1: persistence durability ----
def test_persistence_roundtrip(smoke_dataset, tmp_path):
    from backend.app import pipeline
    from backend.app.persistence import store
    url = f"sqlite:///{tmp_path/'t.db'}"
    inv = pipeline.run(smoke_dataset, window_minutes=10)
    counts = store.persist_investigation(inv, dataset="unit", url=url)
    assert counts["events"] > 0 and counts["entities"] > 0
    # read back in the same process via a fresh session -> proves it's on disk
    summary = store.load_summary("unit", url=url)
    assert summary["events"] == counts["events"]
    assert summary["entities"] == counts["entities"]
