# Changelog

## [1.5.6] — RBL/Finacle SOA profile match (2026-07-28)

`bank_generic` `required_any` / narration aliases missed Finacle SOA headers
(`Tran Particular`, `Debit Amount`, `Tran Date`). Those PDFs scored 0 and landed
in the unrecognised bucket (~58k rows).

- Aliases + gate entries for SOA labels; `Instrument Num.` / `Tran Crncy Code`.
- Measured `fir-65-2024`: transactions **21,052 → 35,870**; unrecognised row
  rejects **→ 0**; MEDIUM still **2**; STRONG still **0** (evidence-blocked).
- First E2E on `fir-0006-2025-u`: 449,567 events / TXN 337,393 / calls 112,174 /
  IP **0** / STRONG **0** / MEDIUM **0** (~60 min cold).

## [1.5.5] — tiered correlation MEDIUM + STRONG (2026-07-28)

FR-9 STRONG (call+IP+txn) is unchanged. Entities that have call+transfer in window W
but no overlapping IP session now surface as **MEDIUM** hits:

- Each hit carries `tier: STRONG | MEDIUM`.
- Summary `correlation_hits` remains STRONG-only; `correlation_hits_medium` is new.
- Risk scoring still uses STRONG only.
- Overview UI shows MEDIUM with a distinct amber treatment.

G5 stays open: STRONG still needs IPDR for numbers present in CDR.

## [1.5.4] — Common IMEI + IPDR /64 + zip passwords (2026-07-28)

G5 blockers that *are* fixable in code (case still has CDR∩IPDR = 0):

- Auto-load LEA `*Common_IMEI*` spreadsheets as PHONE↔IMEI LINK events.
- IPDR IPv6 /64 enrichment: host-only IP-range sessions inherit the TRAI MSISDN
  on the same /64 (**12** sessions upgraded; **64/69** IP sessions now have PHONE).
- CDR attaches IMEI/IMSI as merge keys only when A-party is the report target.
- `field_mapper` allows one header to fill multiple targets (fixes Target/A alias
  clash that briefly dropped ~78k calls).
- `ERAKSHAK_ZIP_PASSWORD(S)` unlocks encrypted archive members (G4).

Measured on `fir-65-2024`: calls restored **203,046**; phone+IMEI entities **29**;
correlation hits still **0** — IPDR MSISDNs never appear in CDR.

## [1.5.3] — NCRP complaint mapping + FR-9 counterparty transfers (2026-07-27)

Want-vs-get on `fir-65-2024`: correlator works on smoke; real-case FR-9 stays at 0
because **CDR∩IPDR phones = 0**. Recovered what the data actually supports:

- **NCRP complaint PDFs:** field mapper collapses whitespace/newlines in headers;
  parse NCRP `HR:/MIN:/AM/PM:` datetimes; clean `-:account` / `acct\\nLayer` cells;
  aliases for `Account No./ (Wallet /PG/PA) ID`. Example Gujarat complaint
  **0 → 13** transactions; case transactions **20,999 → 21,052**.
- **Safer KYC bridge:** `registered_mobile` attaches only when the event account
  equals the header account (no victim↔mule merge on complaint tables).
- **Correlator:** UPI narration phones count as transfer participants (mirror of
  call caller/callee). Measured **9** entities with TXN-as-counterparty + CALL;
  still **0** with IP because IPDR MSISDNs never appear in CDR.

## [1.5.2] — Gemini fail-fast + offline duration filter (2026-07-27)

Verification F2/F3:

- `llm_planner` now times out Gemini at `GEMINI_TIMEOUT_MS` (default 15s) so Ask
  degrades to the offline planner instead of hanging on DNS/network failures.
- Offline planner covers `calls longer than N minutes|seconds` → `duration >= …`.

## [1.5.1] — plain-text NL answers + Ask / Data quality UI (2026-07-27)

`/v1/query` returned a table of rows plus `explanation` (a description of the
*plan*). An investigator asking "who did X call most often?" needs an answer
sentence, with the rows as evidence and the `spec` as the audit trail.

- `backend/app/search/answer.py` — templates the answer **locally** from
  `QuerySpec` + result rows. Case rows are never sent to the LLM to write prose.
- Response gains `answer: str`. `explanation` stays as the plan description.
- React **Ask** screen (`/ask`): question box, answer, rows, expandable spec.
- React **Data quality** screen (`/quality`): reject register that was API-only.
- Investigations status is a real tri-state (`idle` / `analyzing` / `ready` /
  `error`) and no longer fires `analyze` for every dataset at once.
- Streamlit Ask tab shows the same answer + spec expander.

Measured on the synthetic DSL fixture: *"who did X call most often?"* →
`Most frequent contact: +919876543210 — 2 calls.`

## [1.5.0] — recover Finacle bulk + exchange ledgers + IPDR tab text (2026-07-27)

Validating `fir-65-2024` after `da97dd0` still showed **18,721 / 20,033 bank rows
rejected** and the IPDR range `.txt` rejected as an unrecognized source (9/9).

Three mapping/parsing classes, traced from the data-quality reject list:

1. **Finacle/IndusInd bulk SOA** (`FORACID`, `DEDIT_AMOUNT`, `TRAN_PARTICULAR`, …) —
   account and debit columns were not aliases on `bank_generic`, so every row of
   `statement bulk.xls` (6,975) lost its primary identifier.
2. **Exchange / P2P wallet ledgers** (`Time`, `User ID`, signed `Amount`, `Currency`) —
   matched `bank_generic` at 0.25 via Description, then lost every row for a missing
   timestamp. New profile `crypto_exchange_ledger`; `_norm_bank` accepts a signed
   single-column amount and tags non-INR currency as `CRYPTO:<token>`.
3. **Tab-separated IPDR** — `tabular.read` now sniffs the delimiter (`sep=None`).
   `ipdr__1365.txt` becomes `IPDR`/`ipdr_iprange`; its 7 real sessions dedupe
   against the existing `.xlsx` (ip_sessions stays 65 — honest no-op on that metric).

Measured on `fir-65-2024` window 10 after rebuild:

| Metric | Before | After |
|---|---:|---:|
| Transactions | 8,414 | **20,999** |
| Transfers | 5,832 | **12,527** |
| Bank rejected | 18,721 | **4,665** |
| Rejected rows | 167,448 | **154,885** |
| Correlation hits | 0 | 0 (still G5) |

ruff clean; **119** tests pass (3 new regression shapes).

## [1.4.0] — depth/scale remediation (remaining gap-analysis items)

- **B4** bank profiles broadened to real Indian statement columns (Dr_Amt/Cr_Amt/Tran_Date/
  Ac_No/acct_number…) + per-row account support → real SOA/ICORE statements parse with amounts.
- **A5** bank running-balance consistency validation (`normalization/validation.py`) surfaced
  as a data-quality report.
- **A4** crypto FX valuation — config `crypto_rates_inr`, per-transfer `value_inr`.
- **C2** IPDR subscriber MSISDN derived from filename when the sheet lacks it.
- **C4** account-style UPI VPAs link to the payee account; **C5** structured payee-name extraction.
- **C3** fuzzy same-entity *suggestions* (review-only, never auto-merged) — `entity_resolution/suggestions.py`.
- **G2** pipeline split into `run_base` (window-independent, cached) + `apply_analysis`
  (correlation/detection/graph) — window changes no longer re-parse.
- **G1** per-file row cap (logged, not silent) for pathological inputs.
- **E4** graph ego-focus + risk/degree threshold controls; **E5** timeline downsampling.
- **B5** manual column-mapping UI (`ingestion/mapping_writer.py`) — saves a custom profile.
- Dashboard: added **Quality** (rejects/balance-breaks/fuzzy) and **Mapping** tabs (now 11 tabs).

## [1.3.0] — gap-analysis remediation (correctness, PS gaps, detection, bonus)

Closed the issues in `docs/gap_analysis.md`.

### Correctness (🔴)
- **A1 Timezone**: per-source timezone (`source_tz`, crypto=UTC) normalized to canonical IST
  — fixes the 5.5h skew that corrupted crypto timeline/correlation.
- **A2 Dedup**: duplicate events (same data in `.csv` + `- Reports.xlsx`) dropped on a natural
  key; reported as a reject entry.
- **A3 Per-asset**: every Event/transfer tagged with `asset` (INR vs `CRYPTO:<token>`);
  structuring threshold and rapid-forward computed within a single asset only.

### PS gaps (🟠)
- **B1** `.docx` table ingestion (bank/account Word docs). **B2** all Excel sheets read
  (best-sheet selection). **B3** per-file/per-reason reject report (`reject_report()`).
- **E1** Search now filters by **location** (+ date range) — FR-15 fully met.
- **E2** Forensic report embeds **charts** (top-risk bar, activity timeline) — FR-16 met.

### Detection (🟠)
- **D1** min-amount gates on circular-flow/layering (cut INR false positives; crypto kept).
- **D3** new typologies: **comm_burst**, **dormant_activation** (+ added to ML features).

### Bonus (🔵)
- **F2** STR upgraded to FIU-IND-style per-subject entries. **F3** risk **heat map** tab
  (entities × typologies). **F1** rule-based **natural-language query** tab + `search/nl_query.py`.

## [1.2.0] — real hackathon case-data support (FIR 65-2024, FIR-0006-2025 U)

Adapted the backend to ingest and fuse the **actual forensic case folders** (see
`docs/real_data_support.md`). Verified: FIR-65 → ~102k events, crypto circular-flow +
layering detected; FIR-6 → ~155k events incl. 45,585 bank txns, rapid-in-out + structuring
detected. Persist + PDF report confirmed on real data.

### Added
- Real mapping profiles: `cdr/vodafone_idea`, `cdr/lea`, `cdr/reports`, `ipdr/iprange`,
  `crypto/tron_wallet`. Profile loader now discovers any `config/profiles/<group>/`.
- Ingestion: CSV **preamble/header detection**, legacy **.xls** (xlrd), quoted-value
  stripping, ragged-row tolerance, `include_pdf` opt-out + PDF size cap, `~$`/`._` skip.
- Datetime: split date+time columns and `yyyymmdd`/`hhmmss` integer formats.
- Normalizers: real CDR (A/B party, split date+time, call-type directions), IPDR (IP-range,
  IP-primary entities), **crypto → money-flow TRANSACTION**.
- Graph: sampled betweenness centrality for large real graphs (>800 nodes).
- Dashboard/API discover real case folders in `datasets/`; dashboard "Parse PDFs" toggle.

### Fixed
- **CDR IMEI/IMSI over-merge**: these belong to the report's target subscriber, not each
  row's A-party — now attributes only, not merge keys (C3 breaker had flagged 1354-id blobs).
- Row-index crash on non-integer DataFrame indices (`int(r)` → `enumerate`).

## [1.1.0] — 2026-07-08 — Production-readiness remediation (review board fixes)

### Security & reliability (blockers)
- **C1** Persistence layer: durable canonical store (SQLite default / Postgres via
  `DATABASE_URL`) — `persistence/store.py`, `models/canonical.py` now actually used;
  `pipeline.run(persist=True)`, `run_pipeline --persist`, API `analyze{persist:true}`.
- **C2** AuthN/AuthZ: JWT bearer auth (bcrypt hashes), RBAC, `/v1/auth/token`, all data
  endpoints protected, audit logging, consistent error schema, dashboard login gate.
- **C3** Fixed CGNAT entity over-merge: public IP is no longer a merge key; added a
  component-size circuit breaker. Regression test added.
- **C4** Bounded `simple_cycles` (count + time) and layering DFS (path budget).

### High
- **H1** Structured logging (`core/logging_config.py`); removed silent excepts.
- **H2** Upload hardening: filename sanitization (no path traversal), extension/size/count limits.
- **H3** Correlation optimized from O(T·C) to sorted + binary search.
- **H4** Pinned all dependencies to exact versions.
- **H5** CI workflow (ruff + pytest + docker build); ruff config; lint clean.
- **H6** Tests expanded 8 → 18: API auth, CGNAT regression, parser robustness, persistence.

### Medium
- **M2** `/v1` API versioning. **M3** consistent error schema. **M7** Isolation Forest model
  persisted + versioned (`data/models/`).

## [1.0.0] — 2026-07-08 — Full core pipeline (Phases 0–9)

### Added
- **Phase 0** — repo scaffold, config, canonical SQLAlchemy schema, synthetic data generator
  (entity-first, planted labeled fraud, ground truth).
- **Phase 1** — ingestion: format/type/profile auto-detection; Excel/CSV/PDF parsers; reject log.
- **Phase 2** — normalization (phone/IP/datetime/amount), narration mining, provenance; deterministic
  graph-based entity resolution (bank↔telecom fusion via registered mobile).
- **Phase 3** — per-entity unified timeline; windowed call+IP+transfer correlation.
- **Phase 4** — rules (structuring, rapid in/out, layering, circular flow, mule, coincidence) +
  Isolation Forest + composite risk score; ground-truth evaluation (**recall 1.0** on demo).
- **Phase 5** — money-flow (shared-UTR) + communication graph; centrality/community metrics.
- **Phase 6** — Streamlit investigator dashboard (overview, network, entities, timeline,
  correlations, search, report export).
- **Phase 7** — forensic report (PDF + Word) with STR draft and provenance.
- **Phase 8** — CLI runner, pytest suite (8 tests passing), docs.
- **Phase 9** — FastAPI service, Dockerfile, docker-compose.

### Fixed
- ISO vs dd/mm/yyyy date parsing (dayfirst) — was collapsing transaction times.
- Layering DFS first-hop guard — rule now fires correctly.
- Profile confidence scoring (per-field, not per-alias) — removed spurious manual-mapping flags.
