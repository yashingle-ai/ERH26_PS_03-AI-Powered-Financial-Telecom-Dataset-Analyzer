# ERakshak — continuation brief

Paste this whole file into Cursor as the opening prompt. It is written to be
self-contained: what the system is, what is broken, how to prove a fix worked, and
which documents to update as you go.

---

## 0. Read these first, in this order

| File | Why |
|---|---|
| `research/01_problem_statement_analysis.md` | The problem statement (ERH26_PS_03) and what it actually asks for |
| `research/02_requirement_analysis.md` | FR-1…FR-12 numbered requirements. **FR-9 is the flagship.** |
| `docs/GAP_ANALYSIS_REAL_DATA.md` | **The live gap register.** Every open gap, measured against real data |
| `GETTING_STARTED.md` | How to run everything; user journeys; feature checklist |
| `docs/canonical_schema.md` | The event/entity model everything normalises into |
| `research/07_architecture_planning.md` | Why it is a modular monolith; the LLM boundary rule |

`docs/gap_analysis.md` is **superseded and stale** — do not trust it as status.
`docs/GAP_ANALYSIS_REAL_DATA.md` replaces it.

---

## 1. What this is

**ERH26_PS_03 — AI-Powered Financial & Telecom Dataset Analyzer.** A forensic tool for
investigators. It ingests bank statements, CDR (call records) and IPDR (IP sessions) from
a real FIR case folder, normalises them into one canonical event/entity/timeline model,
and surfaces cross-domain coincidences.

**FR-9 is the point of the product:** find an entity where a *call*, an *IP session* and a
*money transfer* all occur inside a window `W`. That is the fusion result nothing else in
the investigator's toolkit gives them. Everything else — money flow, risk scoring, the
graph — is supporting cast.

Repo: `https://github.com/yashingle-ai/ERH26_PS_03-AI-Powered-Financial-Telecom-Dataset-Analyzer`

### Stack

- **Backend** FastAPI (`/v1`, JWT + RBAC), Python 3.11, pandas, scikit-learn, networkx
- **Frontend** React 19, TanStack Router/Query, Tailwind 4, shadcn/ui, D3 — port **8080**
- **Dashboard** Streamlit analyst workbench — port **8501**
- **Container** multi-stage Dockerfile, runs as uid 10001, `docker compose up -d --build`

### Pipeline

```
ingestion → normalization → entity resolution → timeline → correlation → detection → graph
```

Source of truth: `backend/app/pipeline.py`, called by `_analyze()` in
`backend/app/api/main.py`.

---

## 2. The datasets

**The two FIR cases are the real datasets. `demo` and `smoke` are synthetic fixtures for
testing the UI — never quote them as results.**

| Dataset | Location | Files | Size |
|---|---|---|---|
| `fir-65-2024` | `datasets/raw/fir-65-2024/` | 505 | 335 MB |
| `fir-0006-2025-u` | `datasets/raw/fir-0006-2025-u/` | 1006 | 676 MB |
| `demo`, `smoke` | `datasets/raw/{demo,smoke}/` | 53 / 20 | tiny |

Both real cases are already staged into `{bank,cdr,ipdr,other}/` subfolders and appear in
the dataset dropdown. The originals are `datasets/FIR 65-2024/` and
`datasets/FIR-0006-2025 U/` (2.0 GB and 2.1 GB, mostly CCTV and photographs the pipeline
cannot read). `scripts/stage_for_upload.py` produced the staged copies.

### Data safety — non-negotiable

- **Real case evidence must never be committed or baked into an image.** `datasets/` is
  deny-by-default in `.gitignore` *and* `.dockerignore`.
- `datasets/raw/demo/` and `datasets/raw/smoke/` are the **only** tracked paths under
  `datasets/`. `/v1/upload` refuses those two names (409) because real evidence landed in
  `datasets/raw/smoke/other/` once already. See `FIXTURE_DATASETS` in `api/main.py`.
- After **every** run: `git status --porcelain` must show no FIR files, no `.env`, no
  `*.db`.
- The LLM planner may receive **only** the question plus field/operator vocabulary.
  **No case records, names, phone numbers or account numbers may ever leave the machine.**
  Enforced by `_assert_no_case_data()` in `backend/app/search/llm_planner.py` and covered
  by tests. Do not weaken it.

---

## 3. Where things stand — measured, not assumed

Run on `fir-65-2024` (505 files, 335 MB), window 10:

| Metric | Value | Verdict |
|---|---|---|
| Files parsed | 929 | ZIPs expand, so > 505 |
| Events | 211,525 | |
| Transactions | 8,414 | was 1,800 before the mapping fix |
| Calls | 203,046 | |
| IP sessions | 65 | **too low** |
| Entities | 4,146 | |
| **Correlation hits** | **0** | **the flagship feature returns nothing** |
| High-risk entities | 0 | follows from the above |
| Rejected rows | 167,448 | surfaced in Data Quality, not hidden |

`fir-0006-2025-u` has **not** been successfully analysed end to end yet.

### Reject rate by source — this is where the work is

| Source | Rejected | of rows | |
|---|---|---|---|
| BANK | 18,721 | 20,033 | **93%** |
| CDR | 55,314 | 226,994 | 24% (mostly duplicates — fine) |
| IPDR | 9 | 9 | **100%** |
| unrecognised | 35,399 | 58,005 | 61% |

Also: **813 of 929 files are flagged `needs_manual_mapping`**, and **750 have no
recognised `source_type`**.

---

## 4. The work, in priority order

### P1 — the remaining 18,721 rejected bank rows

Two bugs of this exact class were just fixed and recovered 6,614 transactions (4.7×).
Commit `da97dd0` is the worked example — read it before starting.

1. `parse_dt` could not read `11DEC2019:09:07:02` (Finacle/ICORE/SAS format), so every row
   in such a statement lost its timestamp.
2. `map_record` let **raw column order** decide which column won a target. `Tran_Date`,
   `pstd_dt` and `value_dt` all alias to `timestamp_start`, so an empty `value_dt`
   overwrote a clean `11-12-2019`.

**Method that found them — reuse it:**

```bash
# 1. Which files lose the most rows?
curl -s -H "Authorization: Bearer $TOK" \
  "http://127.0.0.1:8000/v1/data-quality/fir-65-2024?window=10" | \
  python -c "import sys,json;d=json.load(sys.stdin);\
r=sorted(d['rejects'],key=lambda x:-int(x.get('rejected') or 0));\
[print(x['rejected'],x['rows'],x['reason'],x['file'][-60:]) for x in r[:10]]"

# 2. Take the worst file and trace ONE row through the real code
#    (see §6 — do this INSIDE the API container, but read the OOM warning first)
pf = ing.parse_file(path)
mapped = field_mapper.map_record(pf.records[0], profile)   # did the columns map?
nz.parse_dt(mapped["timestamp_start"])                     # did the value parse?
norm._norm_bank(mapped, pf.header_identity or {}, profile, {})   # None == rejected
```

The reject **reason** string tells you which of the three stages failed. Do not guess —
trace an actual row.

### P2 — IPDR is 100% rejected

9 of 9 rows. Small in row count, but IPDR is one of the three legs of FR-9, so while it
contributes nothing, correlation cannot work even if the bridge exists. Trace it the same
way. Start at `config/profiles/ipdr/generic.yaml` and `_norm_ipdr`.

### P3 — correlation is 0 (gap G5)

**Diagnosed, not a correlator bug.** The correlator is built and unit-tested
(`test_bridge.py`). It returns 0 because **no entity carries both an `ACCOUNT_NO` and a
`PHONE`**, so there is nothing to correlate across. Verified earlier: 7,967 phone-only
entities, 167 account-only, 1 bridged.

Do **not** "fix" the correlator. The options are:
1. Supply `datasets/entity_map.template.csv` filled in with KYC (account ↔ registered
   mobile). This is the fastest route to a non-zero count.
2. Recover more `registered_mobile` from statement header blocks — `header_identity` in
   the bank profile already supports it; check whether real statements carry it.
3. Mine narrations for phone-based UPI VPAs (`9099102222@ybl`) — `narration_extract`
   already does some of this.

**A previous attempt failed and is documented:** mining 730 Word tables produced 33
account↔phone pairs, of which **0** matched an ingested account. Read that section of
`docs/GAP_ANALYSIS_REAL_DATA.md` before repeating it.

### P4 — natural-language query has no answer and no UI

This is the feature the brief asks about, and it is half-built.

**What exists**
- `backend/app/search/dsl.py` — `QuerySpec` (Pydantic) + a local executor. Question →
  validated structured query → executed **locally**. This is the right architecture and
  the PII boundary depends on it.
- `backend/app/search/llm_planner.py` — the only module that talks to an external API
  (Google Gemini, `gemini-flash-lite-latest`, free tier). Sends the question + schema
  vocabulary **only**.
- `backend/app/search/nl_query.py` — offline rule-based fallback, 5 canned phrasings.
- `POST /v1/query/{ds}` — returns `rows`, `matched`, `total`, `truncated`, `window`,
  `engine`, `spec`, `explanation`.

**What is missing**
1. **No plain-text answer.** The endpoint returns a *table of rows* plus `explanation`,
   which is a description of the generated *plan* ("group calls by counterparty, order
   desc, limit 5") — not an answer to the question. An investigator asking *"who did
   9099102222 call most often?"* should get **"Most frequent contact: +919812345678 — 47
   calls between 12 Jun and 3 Aug 2024,"** with the rows as supporting evidence.
   - Add an `answer: str` field to the response, composed **locally from the result set**.
     Template it from the `QuerySpec` (target, aggregate, group_by, window) and the actual
     numbers. **Do not send rows to the LLM to write the sentence** — that breaks the data
     boundary in §2.
2. **No React UI.** `api.query()` is typed in `frontend/src/lib/api.ts` and **nothing
   calls it**. Only the Streamlit `🗣️ Ask` tab does, and it uses the offline engine.
   Build an Ask screen: question box, the plain-text answer, the rows, and the generated
   `spec` shown as the audit trail. **Showing the spec is a requirement, not a nicety** —
   an analyst must be able to see how an answer was derived before relying on it.
3. `/v1/data-quality` and `/v1/suggestions` are also typed with no UI. Data Quality
   matters most: it is where the 167,448 rejected rows become visible.

### P5 — status labelling is misleading

`frontend/src/routes/_app.investigations.tsx:61`:

```ts
status: analyses[i]?.isLoading ? "analyzing" : "ingested"
```

`ingested` actually means "no result — finished, errored, or never started". A dataset
that failed shows the same chip as one that has not been asked for. Give it a real
tri-state including an error state.

That page also fires `useQueries` across **every** dataset at once, which is what
originally triggered concurrent full pipeline runs.

---

## 5. How to validate — generate first, then compare

**The rule: never report a number you have not measured, and always state what you
expected before you look.** Most bugs here were invisible precisely because the pipeline
reported success while dropping data.

For every change:

1. **Record the baseline** — run the pipeline and write the numbers down *before*.
2. **State the expectation** — "this should recover ~N rows in files X, Y".
3. **Change one thing.**
4. **Re-run and diff** every metric, not just the one you targeted.
5. **Explain any metric that moved unexpectedly**, including ones that went *down*.
6. **If a number does not move, say so.** A fix that changes nothing is a finding.

```bash
# baseline / after — the canonical command
python scripts/run_pipeline.py --input datasets/raw/fir-65-2024 --window 10
```

### Expected vs actual, current

| Metric | Now | Target | Basis |
|---|---|---|---|
| Bank reject rate | 93% | < 20% | CDR already achieves 24%, and most of that is legitimate duplicates |
| IPDR reject rate | 100% | < 20% | 9 rows; it either parses or it does not |
| Transactions | 8,414 | ≫ | 18,721 bank rows still rejected |
| Correlation hits | 0 | > 0 | mechanism is built and unit-tested; needs the bridge (P3) |
| Entities w/ account **and** phone | ~1 | > 0 meaningfully | this is the precondition for the line above |
| NL query — plain-text answer | none | every query | P4 |

### Beware of false green

- **A zero is ambiguous.** It looks identical whether a feature works and found nothing,
  or is broken. When a query returns 0, re-run it against data you *know* contains a hit.
  Two "genuine zeros" were confirmed this way; do the same.
- **Do not trust a passing `docker build`.** It says nothing about whether the image runs.
  Check the container: deps present, both entrypoints serve, an endpoint returns real
  data.
- **Docker does not bind-mount the code.** `/app` is `COPY`ed at build time. Editing a
  file on the host and re-running in the container tests the **old** code. Rebuild:
  `docker compose up -d --build`. This produced a false result during this session.

---

## 6. Testing

```bash
# The three CI steps — all must pass
ruff check backend tools scripts
pytest backend/tests -q            # expect 116 passed
docker build -t erakshak:ci .

# Frontend
cd frontend && npx tsc --noEmit && npx vitest run && npm run build
```

Run backend gates **inside the image** — it is the CI environment, and the local `.venv`
is POSIX-layout and unusable on Windows:

```bash
docker compose exec -T api pytest backend/tests -q --no-header -p no:warnings
docker compose exec -T api ruff check backend tools scripts
```

### Test conventions

- `backend/tests/test_real_data_ingestion_fixes.py` — regressions for real-data parsing
  bugs. Fixtures **reproduce the shape** of real files; **no case data is ever committed.**
  New parser bugs belong here.
- `backend/tests/test_upload_api.py` — pins the *refusals* (traversal, size, type, fixture
  datasets), not just the happy path.
- `backend/tests/test_nl_query_dsl.py` — DSL executor against a synthetic investigation;
  no API key needed.
- Test the **no-API-key path**: the system must never hard-depend on network access.

### Two traps that cost real time here

1. **Tests that pass alone and fail in the suite.** Users are seeded once into a
   module-level cache (`security._USERS`), so an earlier module's random password wins and
   every login 401s. Fixtures must force a reseed. Always run the **whole** suite.
2. **Never run `_analyze` in a second process inside the API container.** It loads a
   duplicate ~3.5 GB copy of the investigation on top of the API's cached one and
   OOM-kills the container. Query through the HTTP API, which shares the cache.

### Performance facts you will need

- A cold `fir-65-2024` analysis takes **~10 minutes** (~195 PDFs parsed page by page).
  Not a hang.
- Results are memoised per `(dataset, window)` with a per-key lock, so concurrent
  identical requests share one run. Warm response: **~130 ms**.
- The cache is **in-process**: `docker compose restart api` clears it.
- Container sits at ~3.6 GB during a real run, ceiling 7.6 GB.

---

## 7. Running it

```bash
cp .env.example .env      # set ERAKSHAK_JWT_SECRET + the two passwords
docker compose up -d --build
docker compose ps         # both services must read "healthy"
cd frontend && npm install && npm run dev
```

- React **http://localhost:8080** · Streamlit **8501** · API docs **8000/docs**
- With passwords unset the API generates a random one per boot and logs it:
  `docker compose logs api | grep "generated a random"`. No default credential ships.
- No `GEMINI_API_KEY` → `/v1/query` falls back to the offline engine. Get a free key at
  <https://aistudio.google.com/apikey>.

---

## 8. Documents to update as you work

Keeping these current is part of the task, not an afterthought. The previous gap doc
rotted into claiming "all items remediated" for things that were still broken, and that
cost real debugging time.

| File | When |
|---|---|
| **`docs/GAP_ANALYSIS_REAL_DATA.md`** | **Every time a gap opens, closes or moves.** Update the "Open gaps — start here" table *and* the measured figures. Mark closed gaps CLOSED with before/after numbers |
| `GETTING_STARTED.md` | Any change to setup, journeys, features, or the expected numbers quoted there |
| `docs/api.md` | Any endpoint added or changed |
| `docs/changelog.md` | Notable changes |
| `docs/decisions/ADR-*.md` | Architectural decisions with real trade-offs |
| `.env.example` | Any new env var, with a comment on what it does |
| `README.md` | Only if the top-level pitch changes |

Commit messages should say **what was wrong, why it happened, what was measured** — not
just what changed. `da97dd0` and `e71b4e0` are the pattern.

---

## 9. Ground rules

1. **Measure, do not assume.** Every claim in this file is a measured number; keep it that
   way.
2. **Never drop data silently.** A rejected row must be counted and surfaced with a reason.
   "What the investigator thinks was ingested" and "what the system holds" must be the
   same set — this is a forensic tool and that gap is the difference between evidence and
   noise.
3. **Provenance survives everything.** Every event carries `source_file`, sheet, row.
   Across a ZIP boundary it reads `archive.zip → statement.csv`. Do not flatten it away.
4. **The LLM never sees case data.** §2. No exceptions.
5. **Report failures honestly.** If a fix does not work, say so with the numbers. A
   negative result that redirects effort is worth more than a plausible claim.
6. **Fix the class, not the instance.** The `.env`-not-reaching-the-container bug was
   "fixed" twice by naming one more variable before being fixed properly with `env_file`.
