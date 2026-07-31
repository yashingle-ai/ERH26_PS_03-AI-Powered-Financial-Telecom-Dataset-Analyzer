# The canonical model

Every shape below was **dumped from a live `pipeline.run("datasets/raw/demo")`**, not written from
memory. `demo` is the tracked synthetic fixture, so no real evidence is quoted — and identifier
digits are masked anyway, so that the pre-commit sweep in `RUNBOOK.md` §8 never returns a match a
reader has to think about. If you change any of these, the change ripples through correlation, detection, the graph and
the report — grep before you rename.

---

## 1. Event

One dict per observation. Bank rows, call records and IPDR sessions all normalise to this, which is
the whole point of the tool: three domains on one timeline.

```python
{
  "event_type":     "TRANSACTION" | "CALL" | "IP_SESSION" | "LINK",
  "timestamp_start": datetime,       # tz-aware, ALWAYS IST. Required except for LINK
  "timestamp_end":   datetime | None,
  "amount":          float | None,   # TRANSACTION only
  "direction":       str | None,     # TRANSACTION: CREDIT|DEBIT   CALL: IN|OUT
  "primary":         (type, value) | None,   # the subject this row is *about*
  "counterparty":    (type, value) | None,
  "own_identifiers": [(type, value), ...],   # everything this row proves about `primary`
  "asset":           str | None,     # "INR", or a crypto symbol
  "attributes":      dict,           # domain extras — narration, duration, cell_id, ips
  "provenance":      dict,           # source_file, row, format, profile
  "entity_id":              str | None,  # filled by er.assign_entities()
  "counterparty_entity_id": str | None,
}
```

Real examples, trimmed:

| field | TRANSACTION | CALL | IP_SESSION |
|---|---|---|---|
| `primary` | `('ACCOUNT_NO', '010651333xxxxx')` | `('PHONE', '+9164332xxxxx')` | `('PHONE', '+9164332xxxxx')` |
| `counterparty` | `('BENEFICIARY', 'Tara Dhar')` | `('PHONE', '+9180097xxxxx')` | `None` |
| `own_identifiers` | account + phone | phone | phone + IP + IMEI |
| `direction` | `'CREDIT'` | `'OUT'` | `None` |
| `attributes` | `narration`, `balance`, `ref_no` | `duration`, `call_type`, `cell_id` | `public_ip`, `private_ip`, port |

**`primary` vs `counterparty` is the distinction that has caused the most confusion.** `primary` is
the subject whose record this is — the account holder whose statement it came from. `counterparty` is
the other side. `timeline_builder` uses **primary** semantics; `window_correlator` uses
**participant** semantics (primary ∪ counterparty) and re-derives transactions at
`window_correlator.py:86` to work around the difference. That inconsistency is documented and
deliberate — do not "fix" it without reading `DECISIONS.md`.

### `LINK` — the pseudo-event

```python
{"event_type": "LINK", "timestamp_start": None, "amount": None, "direction": None,
 "primary": ("ACCOUNT_NO", "…"), "counterparty": None,
 "own_identifiers": [("ACCOUNT_NO", "…"), ("PHONE", "+91…")],
 "attributes": {"source": "bank_reply_gujarati"}, "provenance": {"source_file": "…"}}
```

A `LINK` asserts *these identifiers belong to one subject* and nothing else. It contributes **merge
edges only** — never the timeline, never detection, never the graph. It has no timestamp on purpose:
a bank's KYC record is not something that happened.

Three producers, and the difference between them is evidential, not technical:

| producer | source | trust |
|---|---|---|
| `mapping.load_link_events` | `entity_map.csv`, filled by the case officer | highest — a human asserted it |
| `common_imei.load_common_imei_links` | operator `Common_IMEI_Report` | high — the operator's own record |
| `bank_reply_links.load_bank_reply_links` | Gujarati bank KYC replies in the paperwork | high — the bank's own record |

**Nothing else may produce a `LINK`.** Affidavits assert far more (accused ↔ account ↔ IMEI ↔
handset) and are deliberately excluded: an allegation in a legal filing is not a bank record. See
rule 3 in `../../CLAUDE.md`.

---

## 2. Identifier types

The `(type, value)` tuple is the atom of the whole model. Values are **normalised before** they
become tuples — `+91` E.164 for phones, ASCII digits for everything numeric.

| type | normaliser | merge key? |
|---|---|---|
| `PHONE` | `nz.phone` → `+91XXXXXXXXXX` | **yes** |
| `ACCOUNT_NO` | `nz.account_no` | **yes** |
| `IMEI` | `nz._digits` (14–16) | **yes** |
| `IMSI` | `nz._digits` (15, MCC 404/405) | **yes** |
| `IP` | `nz.ip` | no |
| `BENEFICIARY` | raw name | **no — see below** |
| `UPI_ID` | lowercased | no |

**`BENEFICIARY` is not a merge key and must never become one.** A name is not an identity: two
people share a name, and one person is spelled three ways across three banks. Merging on it would
fuse unrelated subjects. Same reasoning closed the `.vcf` question — 45 name↔phone pairs, zero FR-9
impact, because name is not a key.

Merge keys are configured, not hard-coded: `config/settings.yaml` →
`entity_resolution.merge_key_types` = `["PHONE", "ACCOUNT_NO", "IMEI", "IMSI"]`, read via
`config.merge_key_types()`. `max_component_size: 50` is the oversized cap. A deliberate decision
*not* to add `AADHAAR`/`PAN`/`GSTIN` is recorded in `DECISIONS.md` — measured at **1 entity merged**,
not worth three identifier types plus a PII policy.

---

## 3. Entity

```python
"E00000": {
  "identifiers": {("ACCOUNT_NO", "010651333xxxxx"), ("PHONE", "+9193763…"),
                  ("IMEI", "3178108013xxxxx"), ...},   # a set of tuples
  "types":       {"ACCOUNT_NO", "PHONE", "IMEI", "IP"},
  "label":       "Ayushman Chander",
  "oversized":   False,
  "risk_score":  21.8,          # written back by detection.detect()
  "external":    True,          # ONLY on entities created for a counterparty
}
```

Built by `er.resolve()` as connected components over a graph whose edges are "these two identifiers
appeared on one row". `assign_entities()` then stamps `entity_id` onto every event, minting
`external: True` singletons for counterparties never seen as a primary.

**`external` matters for every count you will ever quote.** `inv.summary()["entities"]` counts
**non-external only** — 7,358 on `fir-65-2024` — while `len(inv.entities)` is 26,439 including
counterparty singletons. Both are correct; they answer different questions. Quoting one as the other
has caused confusion twice.

`oversized` is the circuit breaker: a component past the identifier cap is flagged rather than
merged, because one hub identifier (a bank's customer-care number appearing on 3,045 rows) would
otherwise swallow the case into a single entity. It fired correctly on `E03390`.

---

## 4. Transfer — the money-flow edge

```python
{"from_entity": "E00001", "to_entity": "E00012", "amount": 911653.75,
 "asset": "INR", "time": datetime, "ref": "1000001xxxxx"}
```

`graph/money_flow.build_transfers()`. Each real transfer appears **twice** in bank data — a DEBIT on
the payer and a CREDIT on the payee carrying the same UTR/RRN — so matching on `attributes.ref_no`
gives a deterministic directed edge with no UPI resolution needed. Falls back to
`counterparty_entity_id` when the matching leg is absent from the case.

`payer != payee` is enforced in both branches. A self-edge would credit and debit one entity at the
same instant for the same amount, which reads as 100% rapid forwarding and satisfies both halves of
`mule_account` off one row. `features.build` guards it again for callers that build transfers
themselves.

**A `from_entity` always holds a statement.** Both branches take the payer from a DEBIT leg's
`entity_id`, so `txn_count > 0` for payers always. That is why the counterparty fill in
`features.build` only ever fills payees in practice — measured: all 74 filled entities on `demo`.

---

## 5. Risk row

```python
{"entity_id": "E00060", "label": "Simon Tata",
 "risk_score": 10.5,          # 0-100 = 100 * (0.7*min(1, Σ weights) + 0.3*ml)
 "band": "low",               # low [0,39] medium [40,69] high [70,100]
 "ml_score": 0.0,
 "ml_scored": False,          # is that 0.0 a measurement or an absence?
 "rule_flags": [{"rule": "layering", "detail": "...", "weight": 0.15}],
 "typologies_fired": 1,
 "rule_weight_raw": 0.15,     # BEFORE the 1.0 cap
 "rule_component_saturated": False,
 "features": {...13 ML features...}}
```

Four fields exist because of specific ambiguities, all added under rule 5 rather than by changing
`risk_score`:

- **`ml_scored`** — min-max normalisation hands `0.0` both to the least anomalous *fitted* entity and
  to every entity the forest never saw. Without this flag, "examined and unremarkable" and "never had
  a profile" are indistinguishable.
- **`rule_weight_raw` / `rule_component_saturated`** — enabled weights sum to **1.2** against a
  component capped at **1.0**, so six typologies and eight can tie. **No entity on either fixture
  actually exceeds 1.0** — this is preventive, not an observed mis-ranking. Do not cite it as a fixed
  bug.
- **`typologies_fired`** — the tiebreaker. `detection.risk_rank` is the *single* ranking key, shared
  by `/v1/entities`, `/v1/analyze`, the heat map and the report, because two copies drift and then
  two screens disagree about who is worst.

The forest is fitted **only on entities with records of their own**. Fitting it over transfer
counterparties too moved every observed entity's score by up to **12.4 risk points** for reasons
unrelated to its behaviour — see `../COMPONENT_STATUS.md` §6.2.

---

## 6. Correlation hit

```python
{"entity_id": "E00017", "entity_label": "Diya Rattan", "window_minutes": 10,
 "tier": "STRONG",                 # STRONG = call+IP+transfer, MEDIUM = call+transfer
 "transaction": {"time": "...", "amount": 15958.38, ...},
 "call":        {"time": "...", "counterparty_entity_id": "...", ...},
 "ip_session":  {"start": "...", "end": "...", ...},   # absent on MEDIUM
 "explanation": "Transfer of 15958.38 at ... coincided with ..."}
```

Two tiers only — **there is no WEAK tier** anywhere in the code, whatever older notes say.
`inv.correlation_hits` is STRONG; `inv.correlation_hits_medium` is MEDIUM, deliberately separate
fields so the FR-9 headline can never be inflated by adding them together.

`explanation` is written for a human reading a report, not for a machine. Keep it that way.

---

## 7. Reject entry — rule 2's artefact

```python
{"file": "ground_truth.json", "container": None,
 "reason": "file not opened: unsupported type .json",
 "rows": 0, "rejected": 0, "file_skipped": True}
```

Optional keys you will meet: `evidentiary: False` (blank rows, de-duplicated events — dropped but
*not* a loss), `stage`, `content_never_delivered`, `duplicate_of`, `source_type`, `profile`.

`rejected` is the row count to use; `rows` is the table's total. `Investigation.reject_report()`
sorts by size. Served at `GET /v1/data-quality/{ds}`.

**The reason string is the deliverable.** It is read by an investigator deciding whether to chase an
exhibit, so it must say what to *do*: `"placeholder stub … the file's content was never copied into
the evidence set — request the exhibit from the case officer"` rather than `"unreadable"`. One reason
covering two causes is a bug — two were split for exactly that reason (see `GAPS.md` §7.2).

---

## 8. Investigation — the object every stage writes into

`backend/app/pipeline.py`. `run_base()` fills the window-independent prefix; `apply_analysis()`
fills the rest and is the only part that re-runs when `W` changes.

| field | filled by | notes |
|---|---|---|
| `parsed_files` | ingestion | `ParsedFile` list — `headers`, `records`, `source_type`, `value_map`, `rejects` |
| `events` | normalization | the list above |
| `rejects` | every stage | append, never replace — a stage that reassigned this once lost every parse-time reject |
| `entities`, `node_to_entity` | entity resolution | |
| `timeline` | timeline_builder | per-entity, bisect-indexed |
| `transfers` | money_flow | |
| `document_mentions` | search | pointers into paperwork, **not** merge keys |
| `correlation_hits`, `correlation_hits_medium` | correlation | |
| `risk`, `rule_eligibility` | detection | |
| `graph` | graph service | |
| `data_quality` | validation | ledger-consistency breaks |

`inv.summary()` is the headline dict. **Do not change the meaning of a key in it** — rule 5. Add a
companion key instead, which is how `non_evidentiary_rows`, `unmapped_rows`,
`correlation_hits_medium` and `risk_bands` all arrived.
