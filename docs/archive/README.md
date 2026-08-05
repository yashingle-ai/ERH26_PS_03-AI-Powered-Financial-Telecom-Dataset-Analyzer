# Archive — history only, never status

Everything here was true when written and is not now. Nothing in this folder should be used
to decide what to work on. The live index is [`../README.md`](../README.md).

Archived 5 Aug 2026. Files were moved with `git mv`, so `git log --follow` still reaches
their full history.

---

## Why this folder exists

`gap_analysis.md` claimed **"All identified items remediated"** — A1–A5, B1–B5, C2–C5,
D1/D3, E1/E2/E4/E5, F1–F3, G1/G2 all DONE — while `.xls` support was documented but `xlrd`
was never a dependency, `._` sidecars were not skipped, and vendor formats fell through
silently. Someone acted on that status and lost debugging time to it.

It was then superseded by `GAP_ANALYSIS_REAL_DATA.md`, which was itself overtaken and never
retired. By 5 Aug there were **three** gap registers in the repository, two of them wrong,
and no way to tell which was current without reading all three and comparing dates.

**A stale document is worse than a missing one.** A missing document sends you to the code;
a stale one sends you somewhere confidently wrong. Retiring a document is cheaper than the
debugging it causes.

---

## What is here and what replaced it

### Gap registers — three generations

| File | Last true | Replaced by |
|---|---|---|
| `gap_analysis.md` | ~v1.4.0 | already carried a SUPERSEDED banner pointing at the next one |
| `GAP_ANALYSIS_REAL_DATA.md` | 28 Jul | [`../handbook/GAPS.md`](../handbook/GAPS.md) |

`GAP_ANALYSIS_REAL_DATA.md` is worth one specific caution: its headline advice is
*"Highest value next: raise MEDIUM via the account↔phone bridge"*. **That was built on
31 Jul** (`e3a0633`, `entity_resolution/bank_reply_links.py`, on by default, 35 links,
`account+phone` 2 → 30) — and STRONG did not move. Its `G5` row is also superseded: the
missing leg was re-diagnosed as the **IP session**, not the account↔phone link. Acting on
this file today means rebuilding something that exists.

### Status documents overtaken by measurement

| File | Last true | Replaced by |
|---|---|---|
| `changelog.md` | 28 Jul (v1.5.6) | git history — the final week of work is missing entirely |
| `progress.md` | 8 Jul | `../PS_COMPLIANCE_AND_FIX_PLAN.md`. Says "ALL PHASES COMPLETE" before the tool had ever read real evidence |
| `todo.md` | 8 Jul | `../handbook/GAPS.md`. Its Phase 1 items shipped weeks ago |
| `VERIFICATION_2026-07-27.md` | 27 Jul | point-in-time snapshot; `../handbook/README.md` §8.1 carries the current verified state |

### Reference documents superseded by the handbook

| File | Replaced by |
|---|---|
| `api.md` | [`../handbook/API.md`](../handbook/API.md) — the stub listed 3 of 17 endpoints and told you to run `./.venv/bin/uvicorn`, a POSIX path that does not exist on Windows |
| `canonical_schema.md` | [`../handbook/DATA_MODEL.md`](../handbook/DATA_MODEL.md) — dumped from a live run, and it says which identifiers are merge keys |
| `deployment.md` | [`../handbook/RUNBOOK.md`](../handbook/RUNBOOK.md) |
| `investigation_workflow.md` | [`../handbook/README.md`](../handbook/README.md) + `../../GETTING_STARTED.md` |
| `real_data_support.md` | [`../COMPONENT_STATUS.md`](../COMPONENT_STATUS.md) and [`../PARSER_COVERAGE.md`](../PARSER_COVERAGE.md) |

### Spent work orders

These were written to be pasted into another editor as an opening prompt. They were
executed; the resulting code is in `main`. They are kept because they record what was asked
for and what was verified at the time, but they are instructions, not documentation — acting
on them now re-does finished work.

| File | Written | Note |
|---|---|---|
| `HANDOFF_PROMPT.md` | 27 Jul | continuation brief for Cursor |
| `CURSOR_NEXT_PROMPT.md` | 28 Jul | "round 3" work order; its §0 verification table is a useful record of what was independently re-measured |
| `COORDINATION.md` | 29 Jul | protocol for **two agents editing one checkout simultaneously**. Retired because that is no longer the situation. Read it if it ever is again — it exists because `git add -A` from one session swept 581 lines of another's in-progress work into an unrelated commit |

---

## If you are looking for something specific

| Looking for | Go to |
|---|---|
| What is left to do | [`../handbook/GAPS.md`](../handbook/GAPS.md) |
| Whether a requirement passes | [`../PS_COMPLIANCE_AND_FIX_PLAN.md`](../PS_COMPLIANCE_AND_FIX_PLAN.md) |
| What a component does today | [`../COMPONENT_STATUS.md`](../COMPONENT_STATUS.md) |
| Why something was built the way it was | [`../handbook/DECISIONS.md`](../handbook/DECISIONS.md) |
| What changed and when | `git log` — more reliable than `changelog.md` ever was |
