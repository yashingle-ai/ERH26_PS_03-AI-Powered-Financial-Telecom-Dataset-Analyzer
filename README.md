# ERakshak — AI-Powered Financial & Telecom Dataset Analyzer

**Problem Statement:** ERH26_PS_03 — Bank, CDR & IPDR Fusion · **Domain:** Big Data and Analytics

A forensic intelligence platform that ingests heterogeneous **Bank statements, CDR, and IPDR**,
normalizes them onto a **unified entity + timeline model**, correlates events across datasets, detects
suspicious money-flow / communication patterns, and produces investigation-ready forensic output.

> **Planning docs:** see [`research/`](research/) (Docs 00–12). The build follows the phased plan in
> [`research/08_implementation_planning.md`](research/08_implementation_planning.md) and the layout in
> [`research/09_folder_structure.md`](research/09_folder_structure.md).

## Status

All phases built and running end to end on **two real FIR case folders**. As of 5 Aug 2026:
**429 tests pass**, ruff clean, `tsc` clean; 17 API endpoints; **12 of 19 problem-statement
requirements green, 6 amber, 1 red**. The red is FR-9 (temporal coincidence) and it is blocked on
missing IPDR evidence, not on code.

**→ [`docs/README.md`](docs/README.md) — start here.** It is the index: what to read, in what
order, and which documents are archived and must not be used as status.

## Known gaps

**→ [`docs/handbook/GAPS.md`](docs/handbook/GAPS.md)** — every open gap, ranked and sized, with
🟢 markers on what is already finished. Check those markers before starting anything; an earlier
revision of that file sent someone to build a feature that already existed.

Two older gap registers (`gap_analysis.md`, `GAP_ANALYSIS_REAL_DATA.md`) are in
[`docs/archive/`](docs/archive/) and are **not** status.

## Running it

**→ [GETTING_STARTED.md](GETTING_STARTED.md)** — setup, the three ways to run it
(React console, Streamlit dashboard, CLI), a step-by-step walkthrough of every feature,
and troubleshooting.

## Quick start (Phase 0)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Generate a synthetic, fused, labeled dataset (Bank + CDR + IPDR)
python -m tools.synthetic_data_generator.generate --tier smoke --out datasets/raw/smoke
```

Outputs land in `datasets/raw/<tier>/` with a `ground_truth.json` and per-file `metadata`.

## Repository layout

| Path | Purpose |
|------|---------|
| `research/` | Pre-implementation planning documents (00–12) |
| `config/` | Externalized tunables + mapping profiles (window W, thresholds, layouts) |
| `backend/app/` | Backend modules (ingestion, normalization, entity_resolution, correlation, detection, graph, search, reporting, api) |
| `tools/synthetic_data_generator/` | Phase 0 dataset generator |
| `datasets/` | raw / processed / intermediate / external / metadata |
| `data/` | runtime uploads & report outputs (gitignored) |
| `docs/` | delivered docs + ADRs (`docs/decisions/`) |
| `scripts/` | dev/ops helpers |

## License

Internal / hackathon project. Do not commit real case data.
