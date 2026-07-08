# Investigation Workflow (how an analyst uses ERakshak)

1. **Load data** — select a dataset folder (or upload Bank/CDR/IPDR files) in the dashboard.
   Parsers auto-detect format & layout; a parse summary shows rows and any rejects.
2. **Review overview** — headline counts + top risk entities with the reasons they were flagged.
3. **Explore the network** — money-flow (red) and communication (blue) edges; node color = risk,
   size = degree. Central nodes are likely hubs/mules.
4. **Inspect entities** — drill into an entity to see its resolved identifiers (accounts, phones,
   IPs, IMEI) and every rule that fired, with the specific reason.
5. **Follow the timeline** — per-entity unified timeline of transactions, calls, and IP sessions on
   one axis to see behavior in sequence.
6. **Confirm coincidences** — the Correlations tab lists call+IP+transfer coincidences within the
   chosen window W, each with the underlying evidence and provenance.
7. **Search/filter** — by entity, amount range, type, or free text.
8. **Export** — generate a forensic report (PDF/Word) with the summary, correlation evidence,
   money-flow findings, and an STR draft.

## Reproduce end-to-end (CLI)
```bash
# 1. synthetic data (fused + labeled)
./.venv/bin/python -m tools.synthetic_data_generator.generate --tier demo
# 2. run the pipeline and evaluate against ground truth
./.venv/bin/python -m scripts.run_pipeline --input datasets/raw/demo --window 10 --eval
# 3. launch the dashboard
./.venv/bin/streamlit run backend/app/dashboard/app.py
```
