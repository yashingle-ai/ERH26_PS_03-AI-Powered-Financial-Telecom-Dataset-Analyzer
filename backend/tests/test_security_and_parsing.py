"""Tests for review fixes: auth (C2), CGNAT over-merge (C3), parser robustness (NFR-1)."""


from backend.app.api import security
from backend.app.entity_resolution import service as er


# ---- C2: auth ----
def test_password_hash_and_verify():
    h = security._hash("s3cret")
    assert security._verify("s3cret", h)
    assert not security._verify("wrong", h)


def test_jwt_roundtrip_and_rbac_token():
    tok = security.create_access_token("analyst", ["analyst"])
    # decode via the same path get_current_user uses
    import jwt
    payload = jwt.decode(tok, security._secret(), algorithms=[security.ALGORITHM])
    assert payload["sub"] == "analyst"
    assert "analyst" in payload["roles"]


# ---- C3: CGNAT must NOT merge two different subscribers sharing a public IP ----
def test_shared_public_ip_does_not_merge_entities():
    shared_ip = "203.0.113.7"
    events = [
        {"event_type": "IP_SESSION", "primary": ("PHONE", "+919000000001"),
         "own_identifiers": [("PHONE", "+919000000001"), ("IP", shared_ip),
                             ("IMEI", "111111111111111")],
         "counterparty": None, "timestamp_start": None},
        {"event_type": "IP_SESSION", "primary": ("PHONE", "+919000000002"),
         "own_identifiers": [("PHONE", "+919000000002"), ("IP", shared_ip),
                             ("IMEI", "222222222222222")],
         "counterparty": None, "timestamp_start": None},
    ]
    entities, n2e = er.resolve(events)
    e1 = n2e[("PHONE", "+919000000001")]
    e2 = n2e[("PHONE", "+919000000002")]
    assert e1 != e2, "subscribers sharing a CGNAT public IP were wrongly merged"


def test_shared_imei_does_merge():
    events = [
        {"event_type": "CALL", "primary": ("PHONE", "+919000000010"),
         "own_identifiers": [("PHONE", "+919000000010"), ("IMEI", "999999999999999")],
         "counterparty": None, "timestamp_start": None},
        {"event_type": "IP_SESSION", "primary": ("PHONE", "+919000000011"),
         "own_identifiers": [("PHONE", "+919000000011"), ("IMEI", "999999999999999")],
         "counterparty": None, "timestamp_start": None},
    ]
    _entities, n2e = er.resolve(events)
    assert n2e[("PHONE", "+919000000010")] == n2e[("PHONE", "+919000000011")], \
        "same-device phones should merge via shared IMEI"


# ---- NFR-1: parser must not crash on a malformed/empty file ----
def test_parser_handles_empty_and_garbage(tmp_path):
    from backend.app.ingestion import service as ing
    (tmp_path / "empty.csv").write_text("")
    (tmp_path / "garbage.csv").write_text("not,a,known,layout\n1,2,3,4\n")
    results = ing.parse_directory(str(tmp_path))
    # no exception; unknown layouts flagged, not crashed
    assert len(results) == 2
    assert all(r.source_type is None or r.needs_manual_mapping is not None for r in results)
