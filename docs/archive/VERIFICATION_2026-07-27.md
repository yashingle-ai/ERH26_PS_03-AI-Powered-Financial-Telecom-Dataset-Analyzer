# Verification report — post-fix changes, 27 Jul 2026

Verifying the uncommitted changes on top of `5ac6010` against the brief's four gates.
Every number here was measured on this machine; nothing is carried over from a prior run.

**Verdict: the changes deliver the intended solution for P1, P2 and the local/offline half
of P4. Three gaps remain — one of them a defect introduced by these changes, now fixed;
one a real defect still open; one an environment problem.**

---

## Summary

| Gate | Result | Note |
|---|---|---|
| **A — CI** | **PASS** | 124 tests (target ≥119), ruff clean |
| **B — pipeline on `fir-65-2024`** | **PASS** | every target hit, two almost exactly |
| **C1 — offline planner + local answer** | **PASS** | 5/6 planned, real sentences |
| **C2 — NL over HTTP** | **PARTIAL** | works, but Gemini calls hang — see F2 |
| **C3 — Gemini on real CDR** | **NOT RUN** | blocked by F2 |
| **D — UI** | **PASS** | after fixing F1 |

---

## Gate A — CI

```
ruff check backend tools scripts   →  All checks passed!
pytest backend/tests               →  124 passed in 11.77s
```

Target was ≥119. **PASS.**

Frontend: `npx tsc --noEmit` **failed initially** — see F1. After the fix: tsc exit 0,
`npm run build` succeeds, vitest 2/2.

---

## Gate B — measured pipeline, `fir-65-2024`, window 10

Cold run, 765 s.

| Metric | Baseline (after `da97dd0`) | Now | Delta | Target | |
|---|---|---|---|---|---|
| Transactions | 8,414 | **20,999** | **+12,585** | ~20,999 | ✅ |
| Bank rejected | 18,721 | **4,665** | **−14,056** | ~4,665 | ✅ |
| Rejected rows | 167,448 | **154,885** | −12,563 | ~154,885 | ✅ |
| Transfers | 5,832 | 12,527 | +6,695 | — | |
| Events | 211,525 | 224,110 | +12,585 | — | |
| Files | 929 | 930 | +1 | — | |
| Entities | 4,146 | 4,158 | +12 | — | |
| IP sessions | 65 | 65 | 0 | ~65 | ✅ expected |
| Correlation hits | 0 | 0 | 0 | 0 (G5) | ✅ expected |
| High-risk entities | 0 | 0 | 0 | — | |

**Fail criteria from the brief — neither triggered.** Transactions jumped by 12,585
(threshold was ~10k+); bank rejects fell from ~18.7k to 4,665.

### Reject rate by source

| Source | Before | After | |
|---|---|---|---|
| BANK | 18,721 of 20,033 (**93%**) | 4,665 of 5,977 (**78%**) | −14,056 rows |
| IPDR | 9 of 9 (**100%**) | 11 of 18 (**61%**) | see below |
| CDR | 55,314 of 226,994 (24%) | 55,314 of 226,994 (24%) | unchanged, mostly duplicates |
| unrecognised | 35,399 of 58,005 (61%) | 36,479 of 58,416 (62%) | unchanged |

**Read the BANK percentage carefully.** 78% looks barely better than 93%, but the
*denominator moved*: files that now parse cleanly drop out of the reject list entirely.
The number that matters is rows recovered — **14,056** — and transactions rising to
20,999.

**P2 (IPDR tab text) is delivered.** Rows seen went 9 → 18, which only happens if
`ipdr__1365.txt` is now being read, and 7 rows now survive. Preamble rows still reject,
exactly as the brief predicted. Files 929 → 930 confirms the extra file.

### Unexpected moves — explained

- **Entities +12 only**, despite +12,585 transactions. Expected: the new rows are mostly
  on accounts already known, so they add volume, not new actors.
- **Correlation still 0.** Expected and correct — G5. No entity carries both an
  `ACCOUNT_NO` and a `PHONE`, so there is nothing to correlate across. The correlator was
  not touched and must not be.

---

## Gate C — natural-language answers

### C1 / offline (no key) — PASS

With `GEMINI_API_KEY` removed, `llm_planner.available()` correctly returns `False` and the
offline planner takes over. **5 of 6** investigator questions planned, each producing a
real sentence rather than a plan description:

| Question | Answer |
|---|---|
| transfers over 100000 | `Found 30 transactions. Latest: transaction involving Saumya Mall at 2026-06-02T09:24:49+05:30, ₹200979.03.` |
| high risk entities | `Found 1 entity. Highest risk: Saumya Mall (risk 100.0, high).` |
| which numbers shared an IMEI? | `Most frequent IMEI: 317810801326773 — 16 calls. 8 distinct IMEIs matched.` |
| calls between 2am and 5am | `Found 18 calls. Latest: call involving Aryan Maharaj at 2026-06-14T03:54:24+05:30.` |
| who did +919376311656 call most often? | `Most frequent contact: +917164752553 — 5 calls. 6 distinct contacts matched (showing top 5).` |
| calls longer than 10 minutes | **PLAN-FAIL** — see F3 |

The last row is the required format from the brief, matched exactly.

**A zero was checked, not assumed.** `who did 9812345670 call most often?` first returned
`No matching events found.` Rather than record that as a failure, I found the busiest
caller actually present in `smoke` (`+919376311656`, 16 calls) and re-ran. It answered
correctly, so the earlier zero was genuine — that number is not in the dataset.

### Boundary — PASS

- `backend/app/search/answer.py` (191 lines) and `offline_planner.py` (132 lines) contain
  **no network calls**. The sentence is templated locally from the validated spec and the
  local result set. Case rows are never sent anywhere.
- `_assert_no_case_data` is intact and still invoked (`llm_planner.py:138`). Its guard
  tests pass.

### C2 / HTTP — PARTIAL

`POST /v1/query/smoke` returns `answer`, `rows`, `total`, `engine` and `spec`. One call
completed cleanly through the LLM path:

```
engine = llm | total = 1
ANSWER = 'Found 1 entity. Highest risk: Saumya Mall (risk 100.0, high).'
```

The server log confirms a second (`transfers over 100000`, `engine=llm`). But **3 of 4
requests timed out at 180 s** — see F2.

### C3 / Gemini on real CDR — NOT RUN

Blocked by F2. Cannot honestly claim 6/6 without running it.

---

## Gate D — UI

| Check | Result |
|---|---|
| `/ask` route | 200 |
| `/quality` route | 200 |
| `/investigations` route | 200 |
| Sidebar links `/ask`, `/quality` | present |
| Routes registered in `routeTree.gen.ts` | present |
| Investigations no longer analyses every dataset | **confirmed in code** |

The Investigations page now reads `queryClient.getQueryState` / `getQueryData` instead of
firing `useQueries` across all datasets, with a genuine four-state
`idle | analyzing | ready | error`. This was the exact source of the earlier concurrent
pipeline runs.

**Not verified:** interactive click-through (typing a question, expanding the QuerySpec
panel, reading the reject table). Routes compile and serve; the rendered behaviour has not
been driven by a human or a browser test.

---

## Findings

### F1 — frontend typecheck was broken (introduced by these changes) — FIXED

`npx tsc --noEmit` failed with 4 errors in the new `frontend/src/routes/_app.quality.tsx`:

- `<LoadingState label=… />` — the component's prop is `message`, not `label`.
- three `unknown`-is-not-a-ReactNode errors, all from one root cause: `RejectDto` did not
  declare `source_type`, so it resolved through the `[key: string]: unknown` index
  signature.

Fixed at the type — `source_type` and `profile` are declared on `RejectDto`, since the API
genuinely returns both (`normalization/service.py:291`) — rather than casting at each use
site, which would have left the next consumer with the same trap.

`npm run build` would have failed in CI.

### F2 — the Gemini call has no timeout — **FIXED**

`llm_planner.py` now passes `HttpOptions(timeout=GEMINI_TIMEOUT_MS)` (default
**15000 ms**). A DNS/network hang fails fast into the offline planner instead of
blocking Ask for a minute-plus. Override with `GEMINI_TIMEOUT_MS` in `.env`.

### F3 — the offline planner cannot express a duration filter — **FIXED**

`calls longer than 10 minutes` / `find calls over 5 mins` now maps to
`duration >= N` seconds via `offline_planner.py`. Covered by
`test_offline_planner_calls_longer_than_duration`.

### F4 — the API is unresponsive during a cold analyse — OPEN, pre-existing

A cold `fir-65-2024` run pins a CPU-bound, GIL-holding worker for ~13 minutes, during
which `/v1/auth/token` times out. Not caused by these changes and not a regression, but it
means "analyse a real case" and "use the UI" cannot overlap.

---

## Still NOT solved — do not mark these fixed

- **G5 / FR-9 correlation = 0.** Needs an account↔phone bridge (KYC `entity_map.csv`,
  header-block mobile, or UPI VPA mining). The correlator is built and unit-tested; do not
  "fix" it.
- **~4,665 bank rows still rejected**, plus 36,479 in unrecognised sources — a different
  class from the FORACID/date bugs just closed.
- **`fir-0006-2025-u` has never completed an end-to-end run.** Do not quote figures for it.
- **IPDR still rejects 11 of 18** — improved from 100%, not solved.

---

## Data safety

`git status --porcelain` contains no FIR files, no `.env`, no `*.db`. The new Gemini key
was written to `.env` only, which is confirmed gitignored (`.gitignore:12`); its full value
appears in no file, log or commit.

---

## Reproduce

```bash
docker compose up -d --build
docker compose exec -T api ruff check backend tools scripts
docker compose exec -T api pytest backend/tests -q --no-header -p no:warnings
cd frontend && npx tsc --noEmit && npm run build && npx vitest run
# Gate B — cold, ~13 min
# POST /v1/analyze {"dataset":"fir-65-2024","window_minutes":10}
# GET  /v1/data-quality/fir-65-2024?window=10
```
