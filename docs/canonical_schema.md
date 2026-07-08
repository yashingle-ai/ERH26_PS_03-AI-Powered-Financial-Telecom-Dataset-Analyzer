# Canonical Schema

**Implements:** `research/06_data_understanding.md` §4 · **Code:** `backend/app/models/canonical.py`

The single fusion target every parser maps into. All three sources (Bank, CDR, IPDR) normalize into
these tables so events share one entity model and one timeline.

## Tables

### `entity`
| Column | Type | Notes |
|--------|------|-------|
| entity_id | str (UUID) | PK |
| entity_type | enum | PERSON / ACCOUNT / PHONE / IP / UNKNOWN |
| display_label | str | Human label |
| risk_score | float | Set after detection (FR-12) |

### `entity_identifier`  (supports FR-10 linkage)
| Column | Type | Notes |
|--------|------|-------|
| id | int | PK |
| entity_id | FK → entity | |
| id_type | enum | ACCOUNT_NO / PHONE / IP / UPI_ID / IMEI / IMSI / BENEFICIARY |
| id_value | str | Normalized value |
| source | enum | BANK / CDR / IPDR |

Indexed on `(id_type, id_value)` for fast shared-identifier lookup.

### `event`  (the unified timeline record)
| Column | Type | Notes |
|--------|------|-------|
| event_id | str (UUID) | PK |
| event_type | enum | TRANSACTION / CALL / IP_SESSION |
| entity_id | FK → entity | Primary actor |
| counterparty_entity_id | FK → entity | Payee / callee |
| timestamp_start | datetime(tz) | Normalized (FR-7) |
| timestamp_end | datetime(tz) | Calls / sessions |
| amount | numeric(18,2) | Transactions |
| direction | enum | CREDIT/DEBIT (txn), IN/OUT (call) |
| attributes | JSON | Type-specific fields |
| provenance | JSON | `{source_file, sheet, row, offset, profile}` (NFR-7) |

Indexed on `(entity_id, timestamp_start)` and `(event_type, timestamp_start)`.

### `entity_link`  (investigation graph edges)
| Column | Type | Notes |
|--------|------|-------|
| id | int | PK |
| from_entity_id / to_entity_id | FK → entity | |
| link_type | enum | MONEY_FLOW / COMMUNICATION / SHARED_IDENTIFIER |
| shared_id_type | enum | UPI_ID / IP / IMEI / BENEFICIARY (when shared-id) |
| weight | float | Aggregate (count/amount) for graph edges |

## Mapping quick reference

| Source | → event_type | Key identifiers extracted |
|--------|--------------|---------------------------|
| Bank statement row | TRANSACTION | ACCOUNT_NO, UPI_ID, BENEFICIARY (from narration) |
| CDR row | CALL | PHONE (A & B), IMEI, IMSI |
| IPDR row | IP_SESSION | PHONE (MSISDN), IP, IMEI, IMSI |

See `config/profiles/**` for the source-column → canonical-field maps used by auto-detection (FR-4).
