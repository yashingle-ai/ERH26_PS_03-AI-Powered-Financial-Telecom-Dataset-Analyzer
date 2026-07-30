"""FR-15 filters on `/v1/events` — entity, amount, time and location.

All four were reachable only through the `/v1/query` DSL. The primary listing endpoint
filtered by `event_type` alone, so the requirement was satisfied in one place and not the
other, and an analyst working from the UI could not answer it at all.
"""

from __future__ import annotations

import os
from datetime import datetime

import pytest

from backend.app.api.main import _event_location, _parse_bound, _within
from backend.app.normalization import normalizers as nz


@pytest.fixture(scope="module")
def client():
    os.environ["ERAKSHAK_JWT_SECRET"] = "test-secret"
    os.environ["ERAKSHAK_ADMIN_PASSWORD"] = "adminpass"
    from fastapi.testclient import TestClient

    from backend.app.api.main import app
    return TestClient(app)


@pytest.fixture(scope="module")
def auth_headers(client):
    tok = client.post("/v1/auth/token",
                      data={"username": "admin", "password": "adminpass"}).json()
    return {"Authorization": f"Bearer {tok['access_token']}"}

# ── location: tower location OR cell id ───────────────────────────────────────────

def test_location_reads_both_location_and_cell_id():
    """`Field_.LOCATION` maps to `attributes.location` and `Field_.CELL_ID` to
    `attributes.cell_id`. A CDR carrying only a cell id is still located, so matching one
    field would make this endpoint disagree with `/v1/query` about the same event."""
    assert "surat" in _event_location(
        {"attributes": {"location": "Surat Adajan Tower"}}).lower()
    assert "404-05" in _event_location({"attributes": {"cell_id": "404-05-1234-5678"}})
    both = _event_location(
        {"attributes": {"location": "Vapi Town", "cell_id": "404-05-9999"}})
    assert "vapi" in both.lower() and "404-05-9999" in both
    assert _event_location({"attributes": {}}) == ""
    assert _event_location({}) == ""


# ── time bounds ───────────────────────────────────────────────────────────────────

def test_naive_time_bound_is_read_as_the_canonical_timezone():
    """Every event is normalised to IST. Reading a naive `start=2024-05-15` as UTC would
    shift the window 5.5 hours and silently change which events match."""
    parsed = _parse_bound("2024-05-15")
    assert parsed is not None
    assert parsed.utcoffset() == nz.CANONICAL_TZ.utcoffset(None)


def test_time_bound_honours_an_explicit_offset():
    parsed = _parse_bound("2024-05-15T10:00:00+00:00")
    assert parsed is not None and parsed.utcoffset().total_seconds() == 0


@pytest.mark.parametrize("value", [None, "", "not-a-date", "??"])
def test_unparseable_time_bound_is_ignored_rather_than_fatal(value):
    """A bad query string must narrow nothing, not 500 the listing."""
    assert _parse_bound(value) is None


def test_dayfirst_is_assumed_for_indian_date_input():
    parsed = _parse_bound("15/05/2024")
    assert parsed is not None and (parsed.day, parsed.month) == (15, 5)


# ── window membership ─────────────────────────────────────────────────────────────

def _ist(*args):
    return datetime(*args, tzinfo=nz.CANONICAL_TZ)


def test_within_bounds_is_inclusive_and_rejects_missing_timestamps():
    lo, hi = _ist(2024, 5, 1), _ist(2024, 5, 31)
    assert _within(_ist(2024, 5, 15), lo, hi)
    assert _within(lo, lo, hi) and _within(hi, lo, hi)      # inclusive
    assert not _within(_ist(2024, 4, 30), lo, hi)
    assert not _within(_ist(2024, 6, 1), lo, hi)
    # an event with no timestamp cannot satisfy a time filter
    assert not _within(None, lo, hi)
    assert not _within("2024-05-15", lo, hi)


def test_open_ended_bounds_work_in_both_directions():
    ts = _ist(2024, 5, 15)
    assert _within(ts, _ist(2024, 5, 1), None)
    assert _within(ts, None, _ist(2024, 5, 31))
    assert _within(ts, None, None)
    assert not _within(ts, _ist(2024, 6, 1), None)


# ── FR-18 risk heat map ───────────────────────────────────────────────────────────

def test_risk_heatmap_matrix_lines_up_with_its_axes(client, auth_headers):
    """The heat map was Streamlit-only, so the React app could not show which typologies
    drive each risky entity. The matrix must be rectangular and aligned to both axes, or
    the UI silently mislabels which rule fired on whom."""
    r = client.get("/v1/risk-heatmap/demo", headers=auth_headers, params={"top": 5})
    assert r.status_code == 200
    d = r.json()

    assert len(d["matrix"]) == len(d["entities"]) <= 5
    assert all(len(row) == len(d["columns"]) for row in d["matrix"])
    # every column is a rule that actually fired somewhere
    assert set(d["columns"]) <= set(d["rules_evaluated"])
    # entities are ordered by descending risk score
    scores = [e["risk_score"] for e in d["entities"]]
    assert scores == sorted(scores, reverse=True)
    # a listed entity must have at least one non-zero cell — an all-zero row would read as
    # "assessed and clean" when it means the entity should not have been included
    assert all(any(v > 0 for v in row) for row in d["matrix"])


def test_risk_heatmap_reports_coverage_so_an_empty_grid_is_not_ambiguous(client, auth_headers):
    """`entities_scored` vs `entities_with_a_fired_rule` is what lets a caller tell
    "nothing fired" from "nothing was evaluated" — the same distinction the reject report
    draws for rows."""
    d = client.get("/v1/risk-heatmap/demo", headers=auth_headers).json()
    assert d["entities_scored"] >= d["entities_with_a_fired_rule"] >= len(d["entities"])
    assert d["unit"]
