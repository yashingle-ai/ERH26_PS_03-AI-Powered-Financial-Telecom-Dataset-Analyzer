# Runbook — commands, timings, and what goes wrong

Every command here was run on this machine. Windows paths, Git Bash or PowerShell.

---

## 1. Environment — read this before the first command fails

**The shipped `.venv` is POSIX-layout** (`.venv/bin`, no `Scripts/`) and unusable on Windows. Use the
system interpreter with `PYTHONPATH`:

```bash
PYTHONPATH=. python -m pytest backend/tests -p no:warnings
```

Dependencies are already installed against `C:\Python313`. `python -c "import sklearn, pandas,
fastapi, pdfplumber"` confirms it.

**Frontend: call the local binaries directly.** `npx tsc` fetched an unrelated package called `tsc`
and printed *"This is not the tsc command you are looking for"*:

```bash
cd frontend && ./node_modules/.bin/tsc --noEmit
cd frontend && ./node_modules/.bin/vite build
```

If `node_modules` is missing or `node_modules/typescript` is an empty directory, `npm ci` was
interrupted. Recover with:

```bash
cd frontend && npm cache clean --force && rm -rf node_modules && npm ci --no-audit --no-fund
```

That takes ~3 minutes and installs 605 packages. `npm ci` has crashed here with *"Exit handler never
called!"* on a corrupted cache entry — the cache clean is the fix, not a retry.

---

## 2. The gates

```bash
PYTHONPATH=. python -m ruff check backend/ scripts/
PYTHONPATH=. python -m pytest backend/tests -p no:warnings --tb=short
cd frontend && ./node_modules/.bin/tsc --noEmit
cd frontend && ./node_modules/.bin/vite build
```

Expected: **425 tests**, ruff clean, tsc silent, build succeeds. `pytest` prints no summary line
because `addopts = "-q"` is set in `pyproject.toml`; count with
`--collect-only -q | awk -F': ' '/: [0-9]+$/{s+=$2} END{print s}'`.

`eslint` reports **~54 pre-existing prettier errors** in files nobody has reformatted. That is the
baseline, not your regression — compare counts per file before assuming you caused one.

---

## 3. Running the pipeline

```bash
# demo — ~20 seconds, safe to run in the foreground
PYTHONPATH=. python -m scripts.run_pipeline --input datasets/raw/demo --window 10 --eval

# a real case — 20 to 35 minutes. Background it.
PYTHONPATH=. python -m scripts.run_pipeline --input "datasets/raw/fir-65-2024" --window 10 \
  --save out.json > run.log 2>&1 &
```

**Never run three case-scale jobs at once.** Three concurrent passes exhausted memory and killed a
run with `MemoryError` in an unrelated function, which wasted an hour looking in the wrong place. Two
is usually fine; serial is safe.

Where the time goes: ingestion 10–20 min, then graph betweenness on a large graph (185,063 nodes on
`FIR-0006`) another 10–12 min. `apply_analysis` alone, on a cached `run_base`, is ~1 min per window —
which is the whole reason the split exists.

### Ingestion figures only — much faster

```bash
PYTHONPATH=. python -m scripts.measure_ingestion --input "datasets/raw/fir-65-2024" --save out.json
```

This is the **authoritative** source for any ingestion number quoted in the docs. It composes rejects
exactly as `run_base` does and skips correlation/detection/graph, which is where the time goes.

`scripts/census_skipped.py` gives a sub-minute pre-flight estimate and is **explicitly not** the
coverage figure — one archive level, ignores the budget. Do not quote it.

---

## 4. The API

```bash
uvicorn backend.app.api.main:app --reload      # docs at :8000/docs
```

Or in-process, which is how the endpoint smoke was done:

```python
import os; os.environ["ERAKSHAK_ADMIN_PASSWORD"] = "pw"
from fastapi.testclient import TestClient
from backend.app.api.main import app
c = TestClient(app)
tok = c.post("/v1/auth/token", data={"username": "admin", "password": "pw"}).json()["access_token"]
c.get("/v1/entities/demo?limit=5", headers={"Authorization": f"Bearer {tok}"})
```

With no password set the API **generates a random one per boot and logs it once** — grep the log for
`generated a random`. No default credential ships. See `API.md` for all 15 endpoints and the two
gotchas that will otherwise cost you twenty minutes.

---

## 5. Docker

```bash
cp .env.example .env         # ERAKSHAK_JWT_SECRET + the two passwords
docker compose up -d --build
docker compose ps            # both services must read "healthy"
```

Runs as uid 10001. `datasets/` is deny-by-default in `.dockerignore` as well as `.gitignore` — real
evidence must never be baked into an image.

---

## 6. Failure modes seen on this machine

| symptom | cause | fix |
|---|---|---|
| `MemoryError` in an unrelated function | three case-scale jobs at once | serialise |
| `OverflowError: cannot convert float infinity to integer` | a cell that floats to `inf` reaching `int(float(v))` | guarded in `value_typer._as_int`; it silently zeroed **11 CDR files / 118,510 rows** and the file count stayed identical, so nothing looked wrong |
| ~490 prettier errors in one frontend file | an edit flipped it LF → CRLF | `python -c "p='f.ts';b=open(p,'rb').read();open(p,'wb').write(b.replace(b'\r\n',b'\n'))"` |
| `node_modules` empty | a junction into a git worktree that `git worktree remove --force` then deleted | `npm ci`, and never junction it |
| `Package not found` on a `.docx` | a **162-byte placeholder stub** — the content was never delivered | not fixable; it is an exhibit request. 47 of them |
| `'utf-8' codec can't decode byte` on a `.docx` | genuinely corrupt, distinct from the above | recorded as corrupt, not as undelivered |
| `UnicodeEncodeError: 'charmap'` in your own probe | printing Gujarati to a cp1252 stdout | `sys.stdout.reconfigure(encoding="utf-8")` |
| `json.load` fails reading your own probe output | Gujarati written without an encoding | `open(p, encoding="utf-8")` |
| a figure moved and you cannot say why | the dataset **path** changed, not the code | hold the path fixed; see §7 |

---

## 7. Reproducing any figure

Two rules, both learned the hard way:

**Hold the dataset path fixed.** Each case exists twice:

| path | files on disk | `parsed_files` |
|---|---|---|
| `datasets/FIR 65-2024/` (as delivered) | 646 | 952 |
| `datasets/raw/fir-65-2024/` (staged) | 506 | **961** |

Identical events (247,492), transactions (40,309), calls (203,050), entities (7,358) and transfers
(14,217) — but `files` differs because archive members are counted and the two expand differently. An
early A/B moved code *and* path and could attribute nothing. **Every current figure uses the staged
path.**

**Both arms must be the same build.** Switch behaviour with a flag, never compare two runs from
different times:

```bash
ERAKSHAK_BANK_REPLY_LINKS=0 python -m scripts.run_pipeline --input ... --save off.json
ERAKSHAK_BANK_REPLY_LINKS=1 python -m scripts.run_pipeline --input ... --save on.json
```

| flag | default | effect |
|---|---|---|
| `ERAKSHAK_BANK_REPLY_LINKS` | **on** | account↔phone bridge from Gujarati bank KYC replies |
| `ERAKSHAK_VALUE_TYPING` | on | instance-level column typing |
| `ERAKSHAK_STRUCTURE_RECOVERY` | on | broken-grid geometry recovery |
| `ERAKSHAK_PERSIST_MODEL` | **off** | `=1` to write a fitted forest. Off because `detect()` runs on every read of `/v1/analyze`, `/v1/entities` and `/v1/graph`, so saving unconditionally meant each page view rewrote the committed artifact with a model fit on whatever was being browsed |
| `ERAKSHAK_MODEL_DIR` | `data/models` | |
| `ERAKSHAK_CONFIG`, `ERAKSHAK_SCORING_RULES` | `config/*.yaml` | point at alternates |

To compare two runs row by row rather than by headline, dump per-entity output from each arm and diff
the rows — headline totals hide which entity moved, and "3 fired" can be a different 3.

---

## 8. Before you commit

```bash
# rule 4 — no case identifiers in anything under docs/
# Use [0-9], NOT \d: grep's \d is Unicode-aware, so it matches the Gujarati-digit
# example these docs deliberately contain. Two false positives cost ten minutes.
grep -nE "(^|[^0-9])([6-9][0-9]{9}|[0-9]{15,16})([^0-9]|$)" docs/**/*.md CLAUDE.md

# and check what you are ACTUALLY committing, not what you meant to
git status --short
git diff --cached --stat
```

That second check is not boilerplate: four files staged by something other than an explicit `git add`
were committed and pushed, and one of them held live MSISDNs, IMEIs and IMSIs.

`datasets/` is deny-by-default with only `demo` and `smoke` tracked. `/v1/upload` refuses those two
dataset names so real evidence cannot land in a tracked path.
