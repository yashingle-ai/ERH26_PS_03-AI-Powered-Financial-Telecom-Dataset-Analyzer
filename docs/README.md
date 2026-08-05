# ERakshak documentation — what to read

Three people have worked on this repository and each left documents behind. Two successive
gap registers superseded each other and neither was removed, so by 5 Aug there were 32
markdown files with no way to tell live from dead. This file is the entry point; anything
not listed under "current" below is in [`archive/`](archive/) and must not be used as status.

---

## Current — trust these

Read in this order. Stop after 2 if you only need to make a small change.

| # | File | What it gives you |
|---|---|---|
| 0 | [`../CLAUDE.md`](../CLAUDE.md) | **Start here if you are working through an agent.** Five hard rules, the working method, and the traps — each of which invites a specific wrong action |
| 1 | [`handbook/README.md`](handbook/README.md) | What the system is, how to run it, the datasets, the timings |
| 2 | [`handbook/GAPS.md`](handbook/GAPS.md) | **What is genuinely unfinished**, ranked and sized. Check the 🟢 markers before starting anything |
| 3 | [`handbook/DECISIONS.md`](handbook/DECISIONS.md) | Every judgement call and its reasoning. Several look like bugs until you know what was measured |

Then, as needed:

| File | When |
|---|---|
| [`handbook/DATA_MODEL.md`](handbook/DATA_MODEL.md) | **Before writing backend code.** Exact Event / Entity / transfer / risk / reject shapes, and which identifiers are merge keys |
| [`handbook/ARCHITECTURE.md`](handbook/ARCHITECTURE.md) | Before changing any pipeline stage — each stage's contract and why each fallback exists |
| [`handbook/API.md`](handbook/API.md) | All 17 endpoints, plus the four paths you will try that do not exist |
| [`handbook/RUNBOOK.md`](handbook/RUNBOOK.md) | Commands, real timings, failure modes seen on this machine |
| [`handbook/MEASUREMENT.md`](handbook/MEASUREMENT.md) | The A/B protocol, and the figures that were **withdrawn** |
| [`handbook/TESTING.md`](handbook/TESTING.md) | Conventions, the synthetic-fixture rule, why the refusal tests matter most |
| [`COMPONENT_STATUS.md`](COMPONENT_STATUS.md) | Component-by-component reference, 800+ lines. Look things up; do not read straight through |
| [`PS_COMPLIANCE_AND_FIX_PLAN.md`](PS_COMPLIANCE_AND_FIX_PLAN.md) | The 19 problem-statement requirements with measured evidence |
| [`PARSER_COVERAGE.md`](PARSER_COVERAGE.md) | What each reader opens, and what it refuses on purpose |
| [`RETROSPECTIVE_2026-07-30.md`](RETROSPECTIVE_2026-07-30.md) | Hypotheses **falsified** as well as confirmed. Worth reading once for the method |
| [`architecture.md`](architecture.md) | Short module map. The contracts are in `handbook/ARCHITECTURE.md` |
| [`WORK_PLAN_2026-08-05.md`](WORK_PLAN_2026-08-05.md) | The current work plan and its baseline measurements |
| [`EVIDENCE_LEAK_2026-08-05.md`](EVIDENCE_LEAK_2026-08-05.md) | ⚠️ **Open rule-4 finding** — live case identifiers are tracked in git and on the public remote. Awaiting an owner decision |
| [`decisions/`](decisions/) | ADRs |

`../artifacts/` holds the frontend design package — backend understanding, technical
requirements, app flow, UI/UX brief, API consumption guide, review critique, and the
five-sprint implementation roadmap. Sprints 1–4 shipped; Sprint 5 is tracked in the work
plan above.

---

## Who wrote what

| Period | Author | Scope |
|---|---|---|
| 6–17 Jul | Yash Ingle, Himal Rana | Original pipeline (phases 0–9), Streamlit dashboard, research package |
| 17 Jul | tarun | React frontend redesign — Sprints 1–4 of `artifacts/07_implementation_roadmap.md` |
| 25 Jul – 1 Aug | Yash Ingle | Real-evidence hardening: ingestion recovery, entity resolution, detection, and the `handbook/` package |
| 3 Aug | Himal Rana | Durable analysis snapshots, live analyze progress, `.env` loading |
| 5 Aug | tarun | Documentation reorganisation; frontend progress/cache wiring; Sprint 5 |

The folder now called `handbook/` was `yash development/` until 5 Aug. It was renamed
because the space in the path breaks shell globs — it silently mangled a `git log` command
during the audit that produced this file. Its content and authorship are unchanged.

---

## Archived — history only, never status

[`archive/`](archive/) holds documents that were true when written and are not now. Its
[README](archive/README.md) says what each one was and what replaced it.

The reason this matters is recorded in `archive/gap_analysis.md`, which spent weeks
claiming *"All identified items remediated"* for items that were measurably broken. It cost
real debugging time. **A document that is no longer maintained is worse than no document**,
because it is indistinguishable from a maintained one until you act on it.

---

## Keeping this true

Updating documentation is part of the work, not an afterthought.

| File | Update when |
|---|---|
| `PS_COMPLIANCE_AND_FIX_PLAN.md` | any requirement's status or evidence changes |
| `COMPONENT_STATUS.md` | a component gains capability or a decision is taken |
| `handbook/GAPS.md` | a gap opens, closes or is re-sized — **mark 🟢 what you finish** |
| `handbook/DECISIONS.md` | any judgement call a future reader would question |
| `handbook/API.md` | an endpoint is added or changed |
| `PARSER_COVERAGE.md` | a reader is added or its refusals change |
| `.env.example` | any new variable, with a comment on what it does |

If a document goes out of date and you cannot fix it, **move it to `archive/`** rather than
leaving it in place. That is the whole lesson of the two gap registers.

> **Before committing anything under `docs/`**, run the identifier grep from `CLAUDE.md` §1.
> `DECISIONS.md` was once committed carrying live MSISDNs and IMEIs from the case folder.
