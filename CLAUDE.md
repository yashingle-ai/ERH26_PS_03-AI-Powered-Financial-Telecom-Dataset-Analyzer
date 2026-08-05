# ERakshak — brief for an agent picking this up

Forensic data-fusion tool for problem statement **ERH26_PS_03**: ingest bank statements, CDR and
IPDR from a real FIR case folder, resolve one entity/timeline model, surface cross-domain
coincidences. Two Claude sessions built it over several days on **real police evidence**.

Read this file first. Then `docs/handbook/GAPS.md` before choosing work, and
`docs/handbook/DECISIONS.md` before changing anything that looks wrong — several
decisions look like bugs until you know what was measured.

**Current state, verified 5 Aug:** 429 tests pass, ruff clean, `tsc` clean. (31 Jul: 425 tests,
`vite build` succeeds, pipeline runs end to end on `demo` and both real cases, 18/18 API checks.)
**17** API endpoints. Scorecard: 12 green · 6 amber · 1 red.

**Read `docs/README.md` for what to read** — 13 stale documents were moved to `docs/archive/`
on 5 Aug, including two superseded gap registers. `docs/yash development/` is now
`docs/handbook/`. Current work: `docs/WORK_PLAN_2026-08-05.md`.

---

## 1. Five rules. Violating any of these is worse than shipping nothing.

**1 — The LLM never sees case data.** Gemini gets a schema and a question, never rows. Check
`backend/app/search/nl_query.py` before adding anything AI-facing.

**2 — Nothing is dropped silently.** Every unread row, refused file and skipped archive member
lands in `Investigation.rejects` with a reason, served at `GET /v1/data-quality/{ds}`. A log
warning is *not* a reject. When you add a skip path, add the reject entry in the same commit.

**3 — Never fabricate an identity link.** This is the one that nearly caused real harm: a
reference table was almost used to merge **32 mule accounts into ~98 police entities**, caught
only by measuring that its `Mobile Number` column was the *investigating officer's*. Before any
code creates a merge, check officer contamination, cardinality, and what the column actually
means. `has_admin_role_columns()` is the guard; `bank_reply_links.py` is the worked example.

**4 — Real evidence never reaches git.** `datasets/` is deny-by-default in `.gitignore` *and*
`.dockerignore`. This applies to docs written *about* the evidence too —
`docs/handbook/DECISIONS.md` was committed with live MSISDNs and IMEIs in it. Before committing anything under `docs/`:

```bash
# [0-9] not \d — grep's \d is Unicode-aware too, so it flags the illustrative
# Gujarati-digit example in these very docs. Same trap as the bug in §6.
#
# Use `git grep`, NOT `docs/**/*.md`. Without `shopt -s globstar`, bash expands
# `docs/**/*.md` exactly like `docs/*/*.md` — it matches docs/handbook/*.md and
# skips docs/*.md entirely. That is not hypothetical: it is why DECISIONS.md was
# caught and untracked in `abf14dd` while COMPONENT_STATUS.md and
# PS_COMPLIANCE_AND_FIX_PLAN.md kept live case MSISDNs through the same sweep.
git grep -nE "(^|[^0-9])([6-9][0-9]{9}|[0-9]{15,16})([^0-9]|$)" -- '*.md' '*.py' '*.yaml' '*.csv'
```

Scan **every tracked text file, not only `docs/`**. Case identifiers have reached
`backend/tests/`, `config/profiles/`, `backend/app/` and `datasets/entity_map.template.csv`
as well — see `docs/EVIDENCE_LEAK_2026-08-05.md`.

**5 — Never redefine a headline metric. Add a field beside it.** `rejected_rows`,
`rows_in_unrecognised_tables` and `correlation_hits` keep their original meanings so every figure
ever quoted still compares. `unrecognised_by_reason`, `typologies_fired` and `ml_scored` are
companions added under this rule.

---

## 2. How to work here

**Measure before fixing.** Three requirements went green by re-measuring alone — the recorded
figure was stale. **FR-4 was measuring tables when the meaningful unit was rows, and the gap was
twenty times smaller than the headline.** Cheaper than fixing something three times, which has
happened.

**Count the quantity the criterion names.** A probe counted *records* while the criterion counted
*events*; a record survives intact while losing the column that made it mappable. That produced a
false PASS.

**A/B with a flag, never by run timestamp.** Both arms must run the same build. Attributing a
change to code from two runs at different times is unprovable and was withdrawn once.
`ERAKSHAK_BANK_REPLY_LINKS`, `ERAKSHAK_VALUE_TYPING`, `ERAKSHAK_STRUCTURE_RECOVERY` exist for this.

**Hold the dataset path fixed.** Each case exists twice — `datasets/FIR 65-2024/` (646 files as
delivered) and `datasets/raw/fir-65-2024/` (506 staged). Identical events, transactions, calls,
entities and transfers; **`files` reads 952 vs 961**. An early comparison moved code *and* path and
could attribute nothing. All current figures use the staged path.

**A non-empty result is not a correct result.** Recovery once replaced a 10,027-row table with 25
records and the integration accepted it because the output was merely non-empty.

**Read, don't guess.** Time was lost inventing API paths that don't exist (`/v1/timeline`,
`/v1/rejects`) and guessing profile column aliases. Enumerate `main.v1.routes`; read
`config/profiles/*/*.yaml`.

---

## 3. Commands

```bash
# tests + lint  — call the venv interpreter EXPLICITLY.
# Bare `python` is the system 3.13 here; it has no pdfplumber and fails collection on
# 16 files, which reads as a broken checkout and is not one. (The old warning that this
# .venv is POSIX-layout no longer holds — it was recreated on Windows and has Scripts/.)
PYTHONPATH=. ./.venv/Scripts/python.exe -m pytest backend/tests -p no:warnings --tb=short
PYTHONPATH=. ./.venv/Scripts/python.exe -m ruff check backend/ scripts/

# frontend — use the local binaries; `npx tsc` may fetch an unrelated package
cd frontend && ./node_modules/.bin/tsc --noEmit && ./node_modules/.bin/vite build

# authoritative ingestion figures for a case
PYTHONPATH=. python -m scripts.measure_ingestion --input "datasets/raw/fir-65-2024" --save out.json

# full pipeline
PYTHONPATH=. python -m scripts.run_pipeline --input datasets/raw/demo --window 10 --eval
```

A case-scale run is **20–35 minutes**. Run them in the background and **never three at once** —
that exhausted memory and killed a run with `MemoryError` in an unrelated function.

---

## 4. Where things are

| Path | What |
|---|---|
| `backend/app/pipeline.py` | orchestrator. `run_base()` is the window-independent prefix; `apply_analysis()` re-runs per window |
| `backend/app/ingestion/` | readers, `detector.py` (format by magic bytes — extensions lie), `value_typer.py`, `structure.py`, `unrecognised.py` |
| `backend/app/normalization/` | `normalizers/` (E.164, amounts, IST), `field_mapper.py`, `validation.py` |
| `backend/app/entity_resolution/` | `service.py` merge graph, `mapping.py` KYC CSV, `common_imei.py`, `bank_reply_links.py` |
| `backend/app/correlation/window_correlator.py` | FR-9. STRONG = call+IP+transfer, MEDIUM = call+transfer |
| `backend/app/detection/` | `features.py`, `rules.py` (8 typologies), `service.py` (risk = 0.7·rules + 0.3·ML) |
| `backend/app/search/document_mentions.py` | narrative paperwork indexed by identifier |
| `backend/app/core/text.py` | `ascii_digits` — Indic numerals. **One copy. Do not add a second** |
| `config/profiles/*/*.yaml` | schema mapping. `config/scoring_rules.yaml` = thresholds |

---

## 5. Already built. Do not rebuild.

`docs/handbook/GAPS.md` sent someone to build item 3.1 after it existed — check the 🟢
markers there first.

- **Counterparty-side detection features** (`6f7751f`) — entities seen only as somebody else's
  payee now carry fan-in and money flows.
- **MEDIUM into the risk model** (`6f7751f`) — `medium_weight: 0.075` vs STRONG's `0.15`.
- **Per-rule eligibility** (`6f7751f`) — `eligible` was `len(feats)` for 5 of 8 rules, so
  `mule_account` read "9,996 eligible, 0 fired". Now the structural precondition.
- **Account↔phone bridge** (`e3a0633`) — `bank_reply_links.py`, **on by default**, 35 links,
  `account+phone` 2 → 30. All three safety checks passed. **STRONG still did not move.**
- **Indic numerals + the amount bug** (`fa368cd`) — see §6.
- **Document mention index** (`48efb0e`) — `GET /v1/document-mentions/{ds}`.
- **Unrecognised-table reasons** (`c99e1e1`) — FR-4's residue split by cause.
- **Durable analysis snapshots + live progress** (`401ac0d`, `fb0b016`, 3 Aug) — results survive a
  restart; `POST /v1/analyze` takes `force` and returns `from_cache`;
  `GET /v1/analyze/progress/{ds}` reports stage/percent/ETA. `docs/handbook/GAPS.md` §8.

## 6. Traps. Each invites a specific wrong action.

**Do not widen `common_imei.py`'s filename match.** It skips 5 of 8 `Common_*_Report` files and
that looks like free coverage. `Common_A_B_Report` is a *comms* edge whose `Number` column holds
SMS sender IDs like `VG-ViCARE`; `Common_First_Cell_ID_*` holds **cell IDs**, and merging a tower
into a phone entity fuses every handset that used that cell. One of those cell IDs is 15 digits and
passes the IMEI length test — the filename is the only thing keeping it out. Rule 3.
`test_common_imei_refuses.py` pins it.

**Do not build profiles for FR-4.** The genuine parser gap across both real cases is **3 tables
and 92 rows — 0.008% of 1.11 M rows**. 82% of one case's residue is an 11,275-row CCTV log; the
other's largest tranche is 337 officer-bearing registers refused on purpose.

**Do not work FR-9 in code.** Every code-side hypothesis has been built and measured, and each
moved the number it should have without moving STRONG. Attribution is 99.9% correct; the IPDR
covers **19 phones out of 4,026**. Three entities hold call+IP+transaction and the three events
never fall within 60 minutes. It is an exhibit request: **IPDR for phones already in the CDR.**

**`\d` is Unicode-aware.** `re.sub(r"\D", "", …)` *keeps* Gujarati `૦-૯`, so every digit test
passed while the value was never converted and `phone()` returned `+91૯૮૭૬૫૪૩૨૧૦` — unmatchable
against its ASCII twin, across three merge keys, with no reject entry. Use `core.text.ascii_digits`.

**`amount("Rs.75,00,000")` returned `0.75`** — the dot from `Rs.` survived the character filter
while the commas did not. A ₹75-lakh transfer recorded as 75 paise, silently. Not
Gujarati-specific. Loud failures are not the dangerous ones.

**A durable snapshot outlives your code change.** Since 3 Aug a finished analysis is pickled to
`data/analysis_cache/<ds>__w<N>.pkl` and reloaded on restart. So after editing a profile, a
threshold or any pipeline stage, the API keeps serving the **pre-change** figures — and restarting
it does not help, which is exactly the move you will try. Worse for the A/B protocol in §2: a flag
flip does not invalidate a snapshot, so both arms return the same pickle and you measure a
difference of zero and believe it. Pass `force: true`, or clear `data/analysis_cache/`.

**Editing a frontend file can flip it CRLF** and produce ~490 phantom prettier errors. Check
`git diff --stat` for a whole-file rewrite.

**Do not junction `node_modules` into a git worktree.** `git worktree remove --force` follows the
junction and deletes the real directory.

---

## 7. Definition of done

1. `pytest` and `ruff` clean; frontend `tsc` clean if touched.
2. A test that would have caught the bug, not just one that passes.
3. Measured on a real case, both arms same build, with the figure and the **path** quoted.
4. If a claim moved a number, say which change moved it. If it moved nothing, **say that** — three
   claims here were withdrawn for being unattributable or overstated, and that is the norm.
5. Reject entries for any new skip path (rule 2).
6. Update `docs/handbook/GAPS.md` — mark 🟢 what you finished, so the next agent does not
   rebuild it.

Full package in `docs/handbook/`: `ARCHITECTURE.md` (stage contracts), `DATA_MODEL.md`
(**read before writing code**), `RUNBOOK.md` (commands + failure modes), `API.md` (17 endpoints),
`MEASUREMENT.md` (the A/B protocol and what was withdrawn), `TESTING.md`, `GAPS.md`, `DECISIONS.md`.

Deeper reading: `docs/COMPONENT_STATUS.md` (component detail),
`docs/PS_COMPLIANCE_AND_FIX_PLAN.md` (19 requirements, measured evidence),
`docs/RETROSPECTIVE_2026-07-30.md` (hypotheses **falsified** as well as confirmed).
