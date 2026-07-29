# Two agents, one checkout — working protocol

Two Claude sessions are editing this repository at the same time, through **one working
tree and one Docker container**. That sharing has already caused a real problem, so this
file is the contract. Read it before your first edit.

---

## What already went wrong

`git add -A` from session A swept 581 lines of session B's in-progress `value_typer.py`
and its 197-line test into commit `641ef4d`, whose message is about reject accounting and
does not mention them. The code is fine and the suite passes, but the history
misattributes the work and it was committed without knowing whether B considered it
finished.

Nothing was lost. It is recorded here so the same mistake is not repeated, and so B knows
where their code went.

---

## Rules

### 1. Never `git add -A` or `git commit -a`

Stage explicit paths only:

```bash
git add backend/app/detection/rules.py backend/tests/test_detection_rules.py
```

`git add -A` in a shared tree commits whatever the other session happens to have
half-written.

### 2. Check for foreign edits before committing

```bash
git status --porcelain
```

If a file you did not touch is modified, it is the other session's. Leave it. If you
cannot commit yours without theirs, stop and say so rather than bundling them.

### 3. The container is a mutex

There is one API container. `docker compose up -d --build` **kills any pipeline currently
running inside it** — a cold `fir-65-2024` pass is ~13 minutes and `fir-0006-2025-u` is
larger. Four runs were destroyed this way in one session, all self-inflicted.

Before rebuilding:

```bash
timeout 15 docker stats --no-stream --format '{{.Name}} CPU {{.CPUPerc}}' erakshak-api-1
```

Sustained CPU near 100% with multi-GB memory means a pipeline is mid-run. Wait.

Do not gate on a task file merely existing — a file can be non-empty from an earlier step
while the work is still going. Gate on an explicit end marker your own script prints.

### 4. Pull before you push

```bash
git fetch origin && git status -sb
```

### 5. Stay in your lane

| Area | Owner |
|---|---|
| `ingestion/detector.py`, `ingestion/value_typer.py`, `tests/test_value_typer.py` | **Session B** (value-based type inference) |
| `detection/`, `normalization/service.py`, `pipeline.py` summary, `api/main.py`, `reporting/` | **Session A** |
| `config/profiles/**` | whoever is adding one — announce in the commit message |
| `docs/PS_COMPLIANCE_AND_FIX_PLAN.md` | append-only; do not rewrite another session's rows |

Touching a file outside your lane is fine when the work genuinely needs it — say so in the
commit message.

---

## House rules that apply to both sessions

These are not style preferences; each one was paid for in this codebase.

1. **Measure, do not assert.** Every number in a commit message or a doc must have been
   produced on this machine. Several confident claims here were wrong and only measurement
   caught them.
2. **A zero is ambiguous.** It looks identical whether a feature ran and found nothing or
   never ran at all. Re-run against data known to contain a hit.
3. **Never manufacture a finding to make a metric move.** `high_risk_entities = 0` is a
   true statement about this case, and rescaling the bands to produce one would be worse
   than reporting zero. Same for `structuring`: its ₹10 lakh gate is a real regulatory
   threshold, not a tunable.
4. **Do not redefine a headline metric.** Add a field. `rejected_rows` kept its meaning
   when `unmapped_rows` was introduced, so older figures still compare.
5. **Nothing is dropped silently.** A rejected row is counted with a reason; a rule that
   could not run is distinguishable from one that found nothing.
6. **The LLM never sees case data** — question plus schema vocabulary only.
7. **Real evidence never reaches git.** `git status --porcelain` must show no FIR files,
   no `.env`, no `*.db`.
8. **`/app` is `COPY`ed into the image, not bind-mounted.** Editing a file on the host and
   re-running in the container tests the *old* code.

---

## Current state — 29 Jul 2026

`fir-65-2024`, W=10, after this session's fixes:

| Metric | Value |
|---|---|
| files / events | 939 / 239,447 |
| transactions | 36,281 |
| calls / ip_sessions | 203,046 / 120 |
| entities | 4,182 (549 with ACCOUNT_NO, **1** with account+phone) |
| correlation STRONG / MEDIUM | 0 / 2 |
| BANK reject rate | 19% (was 78%) |
| unrecognised files | 712 of 939 |
| tests | 156 |

`fir-0006-2025-u` — 1,006 files, has **never** completed an end-to-end run. In progress.

**Open:** F4b account↔phone bridge · F5 heat map in API/React · F7 `/v1/events` location
filter · nobody has driven `/ask` or `/quality` in a browser.

**Closed, do not reopen:** FR-9 STRONG correlation. The two IPDR MSISDNs, their IMEIs and
IMSIs appear in **zero** files outside `ipdr/`. Evidence gap, not a defect.
