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


def test_refresh_issues_a_new_usable_token(client):
    """Analysing a real case takes ~10 min; a session must be renewable."""
    r = client.post("/v1/auth/token", data={"username": "admin", "password": "adminpass"})
    first = r.json()["access_token"]

    r2 = client.post("/v1/auth/refresh", headers={"Authorization": f"Bearer {first}"})
    assert r2.status_code == 200, r2.text
    second = r2.json()["access_token"]

    # The new token must actually work on a protected route.
    assert client.get("/v1/datasets", headers={"Authorization": f"Bearer {second}"}).status_code == 200


def test_refresh_preserves_roles(client):
    """A refreshed token must not silently widen or drop privileges."""
    import jwt

    from backend.app.api import security
    tok = client.post("/v1/auth/token",
                      data={"username": "admin", "password": "adminpass"}).json()["access_token"]
    new = client.post("/v1/auth/refresh",
                      headers={"Authorization": f"Bearer {tok}"}).json()["access_token"]
    before = jwt.decode(tok, security._secret(), algorithms=[security.ALGORITHM])
    after = jwt.decode(new, security._secret(), algorithms=[security.ALGORITHM])
    assert after["sub"] == before["sub"]
    assert sorted(after["roles"]) == sorted(before["roles"])


def test_refresh_rejects_an_invalid_token(client):
    r = client.post("/v1/auth/refresh", headers={"Authorization": "Bearer not-a-token"})
    assert r.status_code == 401


def test_refresh_requires_a_token(client):
    assert client.post("/v1/auth/refresh").status_code == 401


def test_generated_password_is_logged_at_boot_not_first_login(monkeypatch, caplog):
    """A generated credential must reach the log on startup.

    Seeded lazily it only appears once somebody signs in — but behind compose
    nobody can sign in without first reading it out of the log. Guards the
    lifespan hook: without it the assertion after startup fails.
    """
    import logging

    from fastapi.testclient import TestClient

    from backend.app.api import security
    from backend.app.api.main import app

    monkeypatch.delenv("ERAKSHAK_ANALYST_PASSWORD", raising=False)
    monkeypatch.delenv("ERAKSHAK_JWT_SECRET", raising=False)
    monkeypatch.setattr(security, "_USERS", None)      # force a reseed
    monkeypatch.setattr(security._secret, "_ephemeral", None, raising=False)

    with caplog.at_level(logging.WARNING, logger="erakshak.api.security"):
        with TestClient(app):                          # runs lifespan, no request made
            pass
        text = caplog.text

    assert "generated a random analyst password" in text
    assert "EPHEMERAL" in text


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
