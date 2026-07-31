# ERakshak — start here

You are picking up a working forensic tool for problem statement **ERH26_PS_03**. This
folder is the onboarding entry point: read this file, then the two beside it, then start.
It exists because two Claude sessions built this over several days and most of what
matters is *why* things are the way they are, which no amount of reading the code
recovers.

Everything here was measured on real case data. Where a number is unknown or a claim was
withdrawn, that is stated rather than smoothed over.

---

## 1. Thirty-minute orientation

Read in this order. Stop after step 3 if you only need to make a small change.

| # | File | Why |
|---|---|---|
| 0 | **`../../CLAUDE.md`** | **if you are working through Claude or another agent, start here.** Claude Code loads it automatically every session: the five hard rules, the working method, what is already built, and the traps that each invite a specific wrong action. A human can skip to 1 |
| 1 | **this file** | what the system is, how to run it, where everything lives |
| 2 | **`DECISIONS.md`** (beside this) | every judgement call and its reasoning. Several look wrong until you know what was measured |
| 3 | **`GAPS.md`** (beside this) | what is genuinely unfinished, sized and ranked |
| 4 | `../COMPONENT_STATUS.md` | component-by-component detail, 772 lines. The reference, not the intro |
| 5 | `../PS_COMPLIANCE_AND_FIX_PLAN.md` | the 19 requirements, current status, measured evidence |
| 6 | `../RETROSPECTIVE_2026-07-30.md` | hypotheses confirmed *and falsified*. Read §7 before your first investigation |
| 7 | `../PARSER_COVERAGE.md` | what each reader opens and what it refuses |
| 8 | `../../research/01_problem_statement_analysis.md` | the original problem statement |
| 9 | `../../COORDINATION.md` | only if a second agent is working the repo at the same time |

`docs/gap_analysis.md` is **superseded and stale**. `docs/GAP_ANALYSIS_REAL_DATA.md`
replaced it. Do not trust the old one as status.

---

## 2. What the system is

A forensic data-fusion tool for financial-cybercrime investigators. It ingests **bank
statements, CDR (call records) and IPDR (internet sessions)** from a real FIR case folder,
normalises them onto one entity and timeline model, and surfaces cross-domain
coincidences.

**FR-9 is the point of the product**: find an entity where a *call*, an *IP session* and a
*money transfer* all fall inside a window `W`. Everything else — money flow, risk scoring,
the graph, the report — supports that.

```
ingestion → normalization → entity resolution → timeline → correlation → detection → graph
```

Entry point: `backend/app/pipeline.py`, called by `_analyze()` in `backend/app/api/main.py`.

### Stack

- **Backend** FastAPI (`/v1`, JWT + RBAC), Python 3.11, pandas, scikit-learn, networkx
- **Frontend** React 19, TanStack Router/Query, Tailwind 4, D3 — port **8080**
- **Dashboard** Streamlit analyst workbench — port **8501**
- **Container** multi-stage, runs as uid 10001, `docker compose up -d --build`

---

## 3. Run it

```bash
cp .env.example .env          # set ERAKSHAK_JWT_SECRET + the two passwords
docker compose up -d --build
docker compose ps             # both services must read "healthy"
cd frontend && npm install && npm run dev
```

React **http://localhost:8080** · Streamlit **8501** · API docs **8000/docs**

With the password variables unset the API generates a random one per boot and logs it
once — `docker compose logs api | grep "generated a random"`. No default credential ships
in the image. That is deliberate; see `DECISIONS.md`.

### The four gates

```bash
docker compose exec -T api ruff check backend tools scripts
docker compose exec -T api sh -c "pytest backend/tests -p no:warnings 2>&1 | tail -2"
cd frontend && npx tsc --noEmit && npm run build && npx vitest run
docker build -t erakshak:ci .
```

Run the backend gates **inside the image** — that is the CI environment, and the shipped
`.venv` is POSIX-layout and unusable on Windows.

---

## 4. The datasets

**The two FIR cases are the real data. `demo` and `smoke` are synthetic fixtures for
exercising the UI — never quote them as results.**

| Dataset | Files | What it is |
|---|---|---|
| `datasets/raw/fir-65-2024/` | ~986 tables | real case, CDR-heavy |
| `datasets/raw/fir-0006-2025-u/` | ~1,545 tables | real case, UPI-heavy, 344k transactions |
| `datasets/raw/demo`, `smoke` | 53 / 20 | fixtures only |

The originals are `datasets/FIR 65-2024/` and `datasets/FIR-0006-2025 U/` (2.0 GB and
2.1 GB, mostly CCTV and photographs the pipeline cannot read). `scripts/stage_for_upload.py`
produced the staged copies.

> **Never A/B across the two paths.** Each case exists twice and the `files` count differs:
> `datasets/FIR 65-2024/` holds 646 files as delivered, including TIFs and macOS `._` resource
> forks; `datasets/raw/fir-65-2024/` holds 506 staged with flattened names. Both produce
> **identical** events (247,492), transactions (40,309), calls (203,050), entities (7,358) and
> transfers (14,217) — but `files` reads **952 against 961**, because archive members are counted
> and the two expand differently.
>
> An early comparison here moved the code *and* the path at once and could attribute nothing. Quote
> the path beside any figure, and hold it fixed across both arms of a measurement. Staged
> (`datasets/raw/…`) is the one every current figure in these docs uses.

### Data safety — non-negotiable

- **Real evidence must never be committed or baked into an image.** `datasets/` is
  deny-by-default in `.gitignore` *and* `.dockerignore`.
- `datasets/raw/demo/` and `datasets/raw/smoke/` are the only tracked paths under
  `datasets/`. `/v1/upload` refuses those two names — real evidence landed in
  `datasets/raw/smoke/other/` once already.
- After **every** run: `git status --porcelain` must show no FIR files, no `.env`, no
  `*.db`.
- `artifacts/` is gitignored because scratch scripts written against a live case end up
  embedding real identifiers — a complaint reference was found hardcoded in one.
- **The LLM never sees case data.** Only the question plus field/operator vocabulary.
  Enforced by `_assert_no_case_data()` in `backend/app/search/llm_planner.py`, and the
  answer sentence is composed locally in `answer.py`. Do not weaken either.

---

## 5. Where things stand

**11 green · 7 amber · 1 red** against the 19 requirements. Full table in
`../PS_COMPLIANCE_AND_FIX_PLAN.md` §1.

Measured 30 Jul, `FIR 65-2024`, W=10:

| Metric | 28 Jul | 30 Jul |
|---|---|---|
| files | 930 | 986 |
| events | 238,985 | **246,353** |
| transactions | 35,870 | **39,170** |
| **ip_sessions** | 69 | **4,133** (60×) |
| entities | 4,132 | **6,681** |
| `ACCOUNT_NO` identifiers | 549 | **3,022** |
| account **and** phone | 1 | **3** → later 30 |
| rejected_rows | 140,040 | **118,836** |
| parse seconds | 1,043 | **646** |
| correlation STRONG / MEDIUM | 0 / 2 | 0 / 2 |

`FIR-0006-2025 U`, first ever full run: **456,431 events · 344,055 transactions ·
2 high-risk entities · top score 85.1**.

That last figure matters more than its size — see `DECISIONS.md` §"Risk bands".

**The one red is FR-9**, and it is blocked on evidence rather than code. The account↔phone
bridge was built and measured, and STRONG stayed 0. The missing leg is the **IP session**:
4,133 against 203,050 calls, with only 7 entities holding call+IP at all.

---

## 6. How to work on this — the short version

`DECISIONS.md` has the reasoning. These are the rules that cost the most to learn.

1. **Measure, do not assert.** Every number in a commit message or doc must have been
   produced on this machine.
2. **A zero is ambiguous.** It looks identical whether a feature ran and found nothing or
   never ran. Re-run against data known to contain a hit.
3. **Do not trust a count a feature reports about itself.** MEDIUM=2 was re-derived by
   walking 224k events with an independent bisect before it was believed.
4. **Re-measure before you fix.** Three requirements went green on 30 Jul with *no new
   code* — the recorded figure was simply stale. This is now the first step for any item.
5. **Never manufacture a finding to move a metric.** Add a field instead of redefining a
   headline.
6. **Nothing is dropped silently.** A rejected row is counted with a reason; a rule that
   could not run is distinguishable from one that found nothing; a file never opened is
   recorded.
7. **`/app` is `COPY`ed into the image, not bind-mounted.** Editing a file on the host and
   re-running in the container tests the *old* code. Always `docker compose up -d --build`.
8. **Never run a second `_analyze` inside the API container** — a duplicate ~3.5 GB copy
   OOM-kills it. Go through the HTTP API.
9. **Do not rebuild while a long run is in flight** — it kills it. This happened four
   times in one session, all self-inflicted.
10. **Run the whole suite, never one file** — users seed into a module-level cache, so
    tests can pass alone and 401 together.

### Timings you will need

- A cold `fir-65-2024` analyse is **~11 min**; `FIR-0006-2025 U` is **~49 min**.
- The pipeline is CPU-bound Python holding the GIL, so the API is **unresponsive** for the
  duration. Not a hang.
- Results are memoised per `(dataset, window)` behind a per-key lock, so concurrent
  identical requests share one run. Warm response ~130 ms. The cache is **in-process** —
  `docker compose restart api` clears it.

---

## 7. Feature-flagged recovery paths

Both exist so the two arms of an A/B run the **same build**:

```bash
ERAKSHAK_VALUE_TYPING=0        # disable value-based column inference
ERAKSHAK_STRUCTURE_RECOVERY=0  # disable broken-geometry table recovery
```

This is not a convenience. Attributing a 30,976-event change from run timestamps alone
proved impossible, and two sessions nearly took credit for each other's work as a result.

---

## 8. Reproducing any figure

```bash
python -m scripts.measure_ingestion --input "datasets/FIR 65-2024"
python scripts/run_pipeline.py --input datasets/raw/fir-65-2024 --window 10
```

```
POST /v1/analyze          {"dataset":"fir-65-2024","window_minutes":10}
GET  /v1/data-quality/fir-65-2024?window=10
POST /v1/report/fir-65-2024   {"fmt":"pdf"}
```

---

## 8.1 Verified state, 31 Jul

Checked end to end rather than asserted:

| layer | result |
|---|---|
| tests | **425 passing**, ruff clean |
| frontend | `tsc` clean, `vite build` succeeds |
| pipeline | runs on `demo` and **both** real cases; every stage populates |
| API | **15 endpoints, 18/18 as expected** — including 401 unauthenticated and 400 on a bad report format |
| reports | PDF (`%PDF`, ~96 KB) and DOCX (`PK`, ~116 KB) both generate |

Two things to know about the API surface before you go looking for a bug:

- `app.routes` shows only **6** entries. FastAPI holds an included router as a single
  `_IncludedRouter`, so the 15 `/v1` endpoints do not appear there. A made-up path returns 404
  while `/v1/datasets` returns 401 — enumerate `main.v1.routes`, not `app.routes`.
- There is no `/v1/health`, `/v1/timeline`, `/v1/correlations` or `/v1/rejects`. Health is public
  at `/health`; correlation hits are inside `POST /v1/analyze`; the **reject report** is at
  `GET /v1/data-quality/{ds}`, which matters because that report is how rule 2 is checked.

Newest endpoint: `GET /v1/document-mentions/{ds}?identifier=&kind=` — the narrative paperwork
indexed by the identifiers it names. See `GAPS.md` §7.3 for what it is and is not.

---

## 9. Documents to keep current

Updating these is part of the work, not an afterthought. The original gap doc rotted into
claiming "all identified items remediated" for things that were still broken, and that
cost real debugging time.

| File | When |
|---|---|
| `../PS_COMPLIANCE_AND_FIX_PLAN.md` | any requirement's status or evidence changes |
| `../COMPONENT_STATUS.md` | a component gains capability or a decision is taken |
| `GAPS.md` (this folder) | a gap opens, closes or is re-sized |
| `DECISIONS.md` (this folder) | any judgement call a future reader would question |
| `../PARSER_COVERAGE.md` | a reader is added or its refusals change |
| `../api.md` | an endpoint is added or changed |
| `.env.example` | any new variable, with a comment on what it does |

Commit messages should say **what was wrong, why it happened, and what was measured** —
not just what changed.
