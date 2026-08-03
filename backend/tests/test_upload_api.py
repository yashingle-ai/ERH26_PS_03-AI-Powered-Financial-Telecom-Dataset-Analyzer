"""Upload endpoint: path safety, limits, and honest per-file reporting.

Uploads are attacker-controlled input by definition — a filename is whatever the
client says it is. These tests pin the refusals, not just the happy path.
"""

import io

import pytest


@pytest.fixture(scope="module")
def client():
    import os
    os.environ["ERAKSHAK_JWT_SECRET"] = "test-secret"
    os.environ["ERAKSHAK_ANALYST_PASSWORD"] = "analystpass"
    from fastapi.testclient import TestClient

    from backend.app.api import security
    from backend.app.api.main import app

    # Users are seeded once into a module-level cache. Another test module may have
    # seeded them already — with a random analyst password — in which case setting
    # the env var above has no effect and every login here 401s. Force a reseed.
    security._USERS = None
    return TestClient(app)



@pytest.fixture(scope="module")
def auth(client):
    r = client.post("/v1/auth/token",
                    data={"username": "analyst", "password": "analystpass"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Point DATASETS at a temp dir so tests never write into the real corpus."""
    from backend.app.api import main
    root = tmp_path / "raw"
    root.mkdir()
    monkeypatch.setattr(main, "DATASETS", root)
    return root


def _csv(name="stmt.csv", body=b"date,amount\n2024-01-01,100\n"):
    return ("files", (name, io.BytesIO(body), "text/csv"))


def test_requires_auth(client, sandbox):
    r = client.post("/v1/upload/case1", files=[_csv()])
    assert r.status_code == 401


def test_stores_file_and_reports_it(client, auth, sandbox):
    r = client.post("/v1/upload/case1", files=[_csv()], data={"kind": "bank"}, headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted"] == 1 and body["rejected"] == 0
    assert body["files"][0]["status"] == "stored"
    assert (sandbox / "case1" / "bank" / "stmt.csv").is_file()


def test_creates_dataset_and_kind_subfolder(client, auth, sandbox):
    client.post("/v1/upload/newcase", files=[_csv("cdr.csv")], data={"kind": "cdr"}, headers=auth)
    assert (sandbox / "newcase" / "cdr" / "cdr.csv").is_file()


@pytest.mark.parametrize("ds", ["../escape", "..", "a/b", "a\\b", "", ".hidden", "x" * 65])
def test_dataset_name_traversal_refused(client, auth, sandbox, ds):
    r = client.post(f"/v1/upload/{ds}", files=[_csv()], headers=auth)
    assert r.status_code in (400, 404, 405), f"{ds!r} was not refused: {r.status_code}"
    # Nothing may be created outside the sandbox root.
    assert not (sandbox.parent / "escape").exists()


@pytest.mark.parametrize("name", [
    "../../etc/passwd.csv",          # posix traversal
    "..\\..\\windows\\evil.csv",     # windows traversal
    "/absolute/path.csv",
])
def test_filename_traversal_is_flattened_to_basename(client, auth, sandbox, name):
    r = client.post("/v1/upload/case2", files=[("files", (name, io.BytesIO(b"a,b\n1,2\n"), "text/csv"))],
                    headers=auth)
    assert r.status_code == 200, r.text
    stored = sandbox / "case2" / "other"
    written = list(stored.iterdir())
    assert len(written) == 1
    # The basename survives; every directory component is discarded.
    assert written[0].parent == stored
    assert "/" not in written[0].name and "\\" not in written[0].name
    assert not (sandbox.parent / "etc").exists()


def test_unsupported_type_rejected_with_reason(client, auth, sandbox):
    r = client.post("/v1/upload/case3",
                    files=[("files", ("payload.exe", io.BytesIO(b"MZ\x90"), "application/octet-stream"))],
                    headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["accepted"] == 0 and body["rejected"] == 1
    assert body["files"][0]["status"] == "rejected"
    assert "unsupported" in body["files"][0]["reason"]
    assert not (sandbox / "case3" / "other" / "payload.exe").exists()


def test_oversize_file_rejected_and_partial_write_removed(client, auth, sandbox, monkeypatch):
    from backend.app.api import main
    monkeypatch.setattr(main, "_MAX_UPLOAD_BYTES", 1024)
    r = client.post("/v1/upload/case4",
                    files=[_csv("big.csv", b"x" * 5000)], headers=auth)
    assert r.status_code == 200
    body = r.json()
    assert body["rejected"] == 1 and "limit" in body["files"][0]["reason"]
    # A truncated statement that still parses is worse than no file at all.
    assert not (sandbox / "case4" / "other" / "big.csv").exists()


def test_existing_file_is_never_overwritten(client, auth, sandbox):
    client.post("/v1/upload/case5", files=[_csv("dup.csv", b"a,b\n1,2\n")], headers=auth)
    client.post("/v1/upload/case5", files=[_csv("dup.csv", b"a,b\n9,9\n")], headers=auth)
    names = sorted(p.name for p in (sandbox / "case5" / "other").iterdir())
    assert names == ["dup-1.csv", "dup.csv"]
    assert (sandbox / "case5" / "other" / "dup.csv").read_bytes() == b"a,b\n1,2\n"


@pytest.mark.parametrize("ds", ["demo", "smoke", "DEMO", "Smoke"])
def test_upload_into_a_bundled_fixture_dataset_is_refused(client, auth, sandbox, ds):
    """demo/ and smoke/ are the only paths under datasets/ that git tracks.

    An upload there mixes real evidence into a tracked directory where a later
    `git add -A` would commit it, and no ignore pattern can distinguish an
    uploaded statement from a fixture one — both are a .csv in bank/. This
    actually happened: 711 real case files landed in datasets/raw/smoke/other/
    because the UI prefilled the active dataset name.
    """
    r = client.post(f"/v1/upload/{ds}", files=[_csv()], headers=auth)
    assert r.status_code == 409, r.text
    assert "read-only" in r.json()["error"]["message"]
    assert not (sandbox / ds / "other").exists()


def test_fixture_datasets_remain_readable(sandbox):
    """The guard blocks writes only — analysing the samples must still work."""
    from backend.app.api.main import _dataset_dir
    (sandbox / "demo").mkdir()
    assert _dataset_dir("demo").is_dir()          # read path: allowed


def test_bad_kind_refused(client, auth, sandbox):
    r = client.post("/v1/upload/case6", files=[_csv()], data={"kind": "../evil"}, headers=auth)
    assert r.status_code == 400


def test_mixed_batch_reports_every_file(client, auth, sandbox):
    r = client.post("/v1/upload/case7",
                    files=[_csv("ok.csv"),
                           ("files", ("bad.exe", io.BytesIO(b"MZ"), "application/octet-stream")),
                           _csv("ok2.csv")],
                    headers=auth)
    body = r.json()
    assert body["accepted"] == 2 and body["rejected"] == 1
    # Every submitted file appears — silence about a dropped file is the bug.
    assert len(body["files"]) == 3


def test_upload_invalidates_the_analyze_cache(client, auth, sandbox, monkeypatch):
    """Stale memoised results would report figures predating the upload."""
    from backend.app.api import main
    calls = {"n": 0, "datasets": []}

    def clear(dataset=None):
        calls["n"] += 1
        calls["datasets"].append(dataset)

    monkeypatch.setattr(main._analyze, "cache_clear", clear)
    client.post("/v1/upload/case8", files=[_csv()], headers=auth)
    assert calls["n"] == 1
    # Upload clears the durable snapshot for that dataset, not every key.
    assert calls["datasets"] == ["case8"]


def test_rejected_only_batch_does_not_clear_cache(client, auth, sandbox, monkeypatch):
    from backend.app.api import main
    calls = {"n": 0}
    monkeypatch.setattr(
        main._analyze, "cache_clear",
        lambda dataset=None: calls.__setitem__("n", calls["n"] + 1),
    )
    client.post("/v1/upload/case9",
                files=[("files", ("x.exe", io.BytesIO(b"MZ"), "application/octet-stream"))],
                headers=auth)
    assert calls["n"] == 0
