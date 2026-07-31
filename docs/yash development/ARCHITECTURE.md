# Architecture — the stages and their contracts

> Not the same file as `../architecture.md`. That one is the design-phase **module responsibility
> table** — which package owns what. This one is the **contracts**: what each stage guarantees, what
> the invariants are, and why each fallback exists. Read that for the map, this before changing a
> stage.

```
parse ─► normalise ─► resolve entities ─► timeline ─┬─► correlate ──► detect ──► graph
                                          transfers ┘
        └───────────── run_base() ──────────────────┘└──── apply_analysis() ────┘
             window-INDEPENDENT, 20-35 min              re-runs per window W
```

The split at `run_base` / `apply_analysis` is the single most useful thing to know: changing the
correlation window `W` re-runs only the right-hand side. Cache the left. Every A/B in this project
uses it, and a probe that re-parses per window wastes half an hour a run.

Entry point `backend/app/pipeline.py`. `_analyze()` in `backend/app/api/main.py` is what HTTP calls,
with an `lru_cache` keyed on `(dataset, window)`.

---

## 1. Parse — `backend/app/ingestion/`

**Contract:** a directory in, a `list[ParsedFile]` out, plus every file it declined to open appended
to `skipped_out`.

```python
ParsedFile(path, format, source_type, profile_id, confidence,
           needs_manual_mapping, headers, records, header_identity,
           rejects, container, table_index, value_map)
```

`source_type` is `BANK` | `CDR` | `IPDR` | `CRYPTO` | `None`. **`None` means no profile claimed it** —
and `ingestion/unrecognised.py` classifies *why*, because that distinction decides whether there is
work to do. Across both real cases the genuine parser gap is **3 tables and 92 rows**.

Order of attack, and each fallback exists because the one above it lost real rows:

| step | module | why |
|---|---|---|
| format by **magic bytes** | `detector.py` | extensions lie constantly — `.xls` that is xlsx, `.xlsx` that is an AppleDouble stub, `.xls` that is a text report |
| profile match on headers | `normalization/field_mapper.py` + `config/profiles/` | `required_any` / `required_all` |
| profile may claim on **values** | `value_typer.py` | a headerless statement matches no alias |
| geometry recovery | `structure.py` | broken PDF grids; complaint folder 14 → 389 events |
| fixed-width | `parsers/fixed_width.py` | printed statements with no delimiter; 0 → 743 events |
| HTML tables | `parsers/html_tables.py` | Google legal-process exports; IP_SESSION 69 → 4,133 |

**PDFs are gated on a text layer, not size.** `pdf_has_text_layer()` uses **pdfplumber** — PyMuPDF is
not a declared dependency, do not reach for it. An over-cap PDF *with* text is parsed anyway and the
decision is logged.

Archives recurse 3 levels under a 512 MB budget with path-escape refusal, and **every loss is a
reject entry** — budget exhaustion, depth refusal, encrypted member, unreadable member. That was
added because 534 members vanished silently from one archive.

## 2. Normalise — `backend/app/normalization/`

**Contract:** `list[ParsedFile]` in, `(events, rejects)` out. Everything lands on the canonical Event
of `DATA_MODEL.md` §1.

- `field_mapper.map_record` — profile aliases first, `value_map` last. Non-empty beats empty;
  first-declared alias wins. That ordering fixed `pstd_dt` silently overwriting `Tran_Date`.
- `normalizers/` — `phone` → E.164, `amount` → float, `parse_dt` → **tz-aware IST always**.
  `core.text.ascii_digits` runs first on every numeric: `\d` is Unicode-aware, so Gujarati `૦-૯`
  otherwise survive uncorrected into a merge key.
- **Timezone is per profile.** `source_tz` in the profile, `UTC` for crypto exports and Google HTML,
  IST for everything else. A UTC stamp read as IST is a silent 5.5-hour error that corrupts the whole
  timeline — there is a regression test pinning that a rupee statement can never claim a non-IST
  profile.
- **Dr/Cr follows the balance delta**, not column order. Deciding it alphabetically inverted every
  direction in one file.
- `validation.check_balances` — ledger-consistency breaks, surfaced not fixed.

Rejects here name **which** precondition failed: `no timestamp` (never recoverable — reference data)
versus `has a timestamp but no mapped primary identifier` (a mapping gap). One reason covering both
hid 60,325 rows.

## 3. Resolve entities — `backend/app/entity_resolution/`

**Contract:** `events + link_events` in, `(entities, node_to_entity)` out, then `assign_entities`
stamps ids onto events in place.

Connected components over "these identifiers shared a row", restricted to
`config.merge_key_types()`. `max_component_size: 50` flags oversized components rather than merging
them — one hub identifier would otherwise swallow the case.

Three `LINK` producers feed in here and **only these three may** — see `DATA_MODEL.md` §1. This is
the highest-risk module in the codebase: a wrong merge is rule 3, and the project came within one
measurement of merging 32 mule accounts into ~98 police entities.

## 4. Timeline and transfers

`timeline_builder.build` — per-entity, bisect-indexed, **primary** semantics.
`money_flow.build_transfers` — double-entry matching on shared UTR. See `DATA_MODEL.md` §4.

## 5. Correlate — `backend/app/correlation/window_correlator.py`

**FR-9, the point of the product.** Two tiers, separate fields, never summed:

- **STRONG** — call + IP session + transfer inside `W` for one entity
- **MEDIUM** — call + transfer, no overlapping IP

Uses **participant** semantics (primary ∪ counterparty), unlike the timeline's primary-only. The
mismatch is worked around at `window_correlator.py:86` and is deliberate.

**STRONG is 0 on both real cases at every W from 1 to 60.** Do not treat that as a bug — see
`GAPS.md` §1 and `CLAUDE.md` §6.

## 6. Detect — `backend/app/detection/`

`features.build` → `rules.run_all` + `_ml_scores` → composite:

```
risk_score = 100 * (0.7 * min(1.0, Σ fired weights) + 0.3 * ml_score)
```

Eight typologies in `rules.py`, all thresholds in `config/scoring_rules.yaml`, **nothing
hard-coded**. Every declared threshold must be read by its own rule — three were declared and
ignored, and `test_rule_windows.py` now fails if a fourth appears.

`rules.eligibility_report` is what makes a zero readable: per rule, `enabled` / `eligible` / `fired`,
where `eligible` is the rule's **structural precondition** — not `len(feats)`, which read as
"9,996 eligible, 0 fired" and looked like a broken detector.

The Isolation Forest is fitted **only on entities with records of their own**. Including transfer
counterparties made "a counterparty with one credit" the definition of normal and moved every
observed entity by up to 12.4 risk points.

## 7. Graph, reporting, search

- `graph/service.py` — money-flow + comms graphs, approximate betweenness past ~10k nodes.
- `reporting/service.py` — PDF (reportlab) and DOCX (python-docx). Section 5 is the STR draft,
  section 6 the detection audit. **Never truncate silently**: grounds were cut at 5 and the
  eligibility note at 96 characters, both in the document most likely to be relied on.
- `search/nl_query.py` — Gemini gets a **schema and a question, never rows** (rule 1). Offline
  fallback when no key.
- `search/document_mentions.py` — narrative paperwork by identifier. Pointers, **not** merge keys.

---

## 8. Invariants that cross stages

1. **Timestamps are tz-aware IST** from normalisation onward. A naive datetime downstream is a bug.
2. **`inv.rejects` is appended to, never reassigned.** One stage replaced it and silently lost every
   parse-time reject; that is why the blank-row count read 0 for days.
3. **Identifier values are normalised before becoming `(type, value)`.** Normalising later means two
   spellings of one phone are two entities.
4. **`LINK` events never reach timeline, detection or graph** — merge edges only.
5. **`inv.summary()` keys never change meaning.** Add a companion (rule 5).

## 9. Frontend

React 19 + TanStack Router/Query + Tailwind 4, port 8080. `lib/api.ts` types the wire format,
`lib/mappers.ts` converts to view models — **the boundary where a backend field becomes a UI concept,
and where `ml_scored` stops "not scored" rendering as "0% anomalous"**. A Streamlit workbench on 8501
predates it and still works.

Never verified by a human clicking: `/ask` and `/quality` compile and serve 200, and nobody has typed
a question or read the reject table in a browser. `GAPS.md` §4 ranks that as the cheapest remaining
source of real defects.
