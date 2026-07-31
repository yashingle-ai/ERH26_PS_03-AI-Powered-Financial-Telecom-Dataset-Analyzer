"""A column added to a model must reach a database that already exists.

`Base.metadata.create_all` creates missing *tables* and leaves an existing table's shape
untouched, so adding `RiskAssessment.ml_scored` would have worked on every fresh checkout and
failed with "no such column: ml_scored" on the one machine that had been running longest — the
worst possible distribution of a bug for a forensic tool, because the database that breaks is
the one with the history in it.
"""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

from backend.app.models.canonical import Base, RiskAssessment
from backend.app.persistence import store


def _url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'case.db'}"


def _legacy_db(tmp_path) -> str:
    """A database created before `ml_scored` existed."""
    url = _url(tmp_path)
    eng = create_engine(url, future=True)
    Base.metadata.create_all(eng)
    with eng.begin() as conn:
        conn.execute(text("ALTER TABLE risk_assessment DROP COLUMN ml_scored"))
    with eng.connect() as conn:
        assert "ml_scored" not in {c["name"] for c in inspect(conn).get_columns(
            "risk_assessment")}
    eng.dispose()
    store._engine.cache_clear()
    return url


def test_the_column_is_added_to_a_database_that_predates_it(tmp_path):
    url = _legacy_db(tmp_path)
    eng = store._engine(url)          # the code path that runs on every connect
    cols = {c["name"] for c in inspect(eng).get_columns("risk_assessment")}
    assert "ml_scored" in cols
    store._engine.cache_clear()


def test_a_risk_row_writes_and_reads_back_on_the_upgraded_database(tmp_path):
    url = _legacy_db(tmp_path)
    with store.get_session(url) as s:
        s.add(RiskAssessment(dataset="d", entity_id="E1", label="x", risk_score=50.0,
                             band="medium", ml_score=0.0, ml_scored=False, rule_flags=[]))
        s.commit()
    with store.get_session(url) as s:
        row = s.query(RiskAssessment).one()
        assert row.ml_scored is False, "a persisted 0.0 must stay distinguishable from unscored"
    store._engine.cache_clear()


def test_running_it_twice_is_a_no_op(tmp_path):
    url = _legacy_db(tmp_path)
    store._engine(url)
    store._engine.cache_clear()
    store._engine(url)                # must not raise "duplicate column name"
    store._engine.cache_clear()


def test_a_fresh_database_needs_no_upgrade(tmp_path):
    store._engine.cache_clear()
    eng = store._engine(_url(tmp_path))
    cols = {c["name"] for c in inspect(eng).get_columns("risk_assessment")}
    assert "ml_scored" in cols
    store._engine.cache_clear()
