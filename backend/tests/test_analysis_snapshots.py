"""Durable analysis snapshots: survive API restart; force re-runs the pipeline."""

from __future__ import annotations


def test_analysis_snapshot_roundtrip(smoke_dataset, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'snap.db'}")
    monkeypatch.setenv("ERAKSHAK_ANALYSIS_CACHE", str(tmp_path / "cache"))

    from backend.app import pipeline
    from backend.app.persistence import store

    # Fresh engine (url-cached) for this temp DB.
    store._engine.cache_clear()

    inv = pipeline.run(smoke_dataset, window_minutes=10)
    meta = store.save_analysis_snapshot(
        inv, dataset="smoke", window_minutes=10,
        file_counts={"bank": 1, "cdr": 1, "ipdr": 1, "other": 0},
    )
    assert meta["summary"]["events"] == inv.summary()["events"]
    assert store.has_analysis_snapshot("smoke", 10)

    loaded = store.load_analysis_snapshot("smoke", 10)
    assert loaded is not None
    assert loaded.summary()["events"] == inv.summary()["events"]
    assert len(loaded.entities) == len(inv.entities)

    listed = store.list_analysis_snapshots()
    assert any(r["dataset"] == "smoke" and r["window_minutes"] == 10 for r in listed)

    assert store.delete_analysis_snapshots("smoke", window_minutes=10) == 1
    assert store.load_analysis_snapshot("smoke", 10) is None


def test_analyze_loads_snapshot_instead_of_rerunning(smoke_dataset, tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'snap2.db'}")
    monkeypatch.setenv("ERAKSHAK_ANALYSIS_CACHE", str(tmp_path / "cache2"))

    from backend.app import pipeline
    from backend.app.api import main
    from backend.app.persistence import store

    store._engine.cache_clear()
    main._analyze.cache_clear()

    inv = pipeline.run(smoke_dataset, window_minutes=10)
    store.save_analysis_snapshot(inv, dataset="unit-snap", window_minutes=10)

    calls = []

    def boom(*_a, **_k):
        calls.append(1)
        raise AssertionError("pipeline.run must not be called when a snapshot exists")

    monkeypatch.setattr(main.pipeline, "run", boom)
    monkeypatch.setattr(main.Path, "is_dir", lambda self: True)

    # Point DATASETS/unit-snap resolution: _analyze_uncoordinated checks DATASETS/ds.
    # is_dir is mocked True; load uses our temp DB.
    out = main._analyze("unit-snap", 10, force=False)
    assert out.summary()["events"] == inv.summary()["events"]
    assert calls == []

    # force must re-run
    def fake_run(path, window_minutes=10):
        calls.append(path)
        return inv

    monkeypatch.setattr(main.pipeline, "run", fake_run)
    main._analyze("unit-snap", 10, force=True)
    assert len(calls) == 1
    main._analyze.cache_clear()
