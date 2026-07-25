# Real Case-Data Support (hackathon FIR datasets)

The backend was adapted to ingest the **actual forensic case folders** provided
(`FIR 65-2024`, `FIR-0006-2025 U`) — not just the synthetic data. These folders are large,
heterogeneous dumps (Word/PDF case files, Gujarati documents, images, plus the structured
transaction data). ERakshak focuses on the **structured, analyzable** files and fuses them.

## What is ingested (structured formats)

| Source | Real formats handled | Profile | → Canonical |
|--------|----------------------|---------|-------------|
| **CDR** | Vodafone-Idea (`A PARTY/B PARTY…` + preamble), LEA/"Ticket" (quoted, `Calling/Called Party`), merged **"- Reports.xlsx"** (`A PARTY \| B PARTY \| DATE \| TIME …`) | `cdr/vodafone_idea`, `cdr/lea`, `cdr/reports`, `cdr/generic` | CALL |
| **IPDR** | IP-usage ranges (`IP \| VALUE \| F DATE \| F TIME \| T DATE \| T TIME`, IPv6, `yyyymmdd`/`hhmmss`) | `ipdr/iprange` | IP_SESSION |
| **Crypto** | Tron wallet exports (`Txn Hash, Time(UTC), From, To, Amount, Token Symbol`) | `crypto/tron_wallet` | TRANSACTION (money-flow) |
| **Bank** | Statement-of-account XLSX/XLS (`SOA_*.xlsx`, `ICORE_STMT_*`, bank `.xls`) | `bank/generic` | TRANSACTION |
| **Registry** | NCRP complaint/account lists (reference) | (parsed, entity context) | — |

Ingestion additions for real data:
- **Preamble detection**: locates the true header row under a metadata preamble in CSVs.
- **.xls (legacy)** support via xlrd, alongside .xlsx.
- **Quoted values** (`'919099102222'`) stripped; ragged rows skipped.
- **PDF opt-out** (`include_pdf=False`, default in dashboard for real cases) + size cap —
  real cases have many large narrative/scanned PDFs that carry no structured tables.
- Office lock files (`~$…`, `._…`) skipped.

## Verified results on the real cases

| Case | Events | Bank txns | Calls | Crypto | Entities | Detections |
|------|--------|-----------|-------|--------|----------|-----------|
| **FIR 65-2024** | ~102k | — | ~101.5k | 554 | 2,042 | **circular-flow + layering** across the Tron wallets |
| **FIR-0006-2025 U** | ~155k | 45,585 (10,330 transfers) | ~109k | — | 718 | **rapid-in-out + structuring** on specific accounts (incl. a Sr.Citizen mule) |

Both complete in <70s; entity over-merge circuit breaker active; large-graph centrality
uses sampled betweenness.

## Run it
```bash
# CLI
./.venv/bin/python -m scripts.run_pipeline --input "datasets/FIR 65-2024" --window 15 --persist
# Dashboard (select the case folder in the sidebar; leave "Parse PDFs" off)
./.venv/bin/streamlit run backend/app/dashboard/app.py
```

## Finance ↔ telecom bridge (enabling cross-domain correlation)

The call+IP+transfer coincidence (FR-9) needs a shared identifier linking a bank account /
wallet to a phone. Two bridges are now supported:

1. **Automatic — UPI-VPA phone mining.** Bank narrations carry phone-based UPI VPAs
   (`9876543210@ybl`), extracted (`narration.py`) and set as the counterparty PHONE. This
   unifies a bank *counterparty* with the CDR subscriber of the same number → a
   **cross-domain graph link** ("this account paid phone X, whom we have call records for").
   Note: it links the *counterparty*, not the account *holder*, so on its own it enriches the
   network but does not usually produce a same-entity FR-9 coincidence (that needs the
   holder's phone — bridge #2).
2. **Supplied — analyst KYC / entity map.** Drop an `entity_map.csv` in the case folder to
   authoritatively merge identifiers (the real-world answer — investigators hold CAF/KYC).
   See `datasets/entity_map.template.csv`:
   ```csv
   account_no,phone,wallet,upi_id
   50200099412403,9876543210,,
   ,8058053853,THX65Zgrr63zCBwMcDnDqnd6bCodNYiT4q,
   ```
   (Or generic per-link rows: `type_a,value_a,type_b,value_b`.) The pipeline merges these
   into one entity, so that entity's transfers, calls, and IP sessions land on one timeline
   and cross-domain coincidences surface.

## Known gaps / honest limitations
- **Cross-domain correlation is data-dependent.** With no phone-based VPA overlap and no
  `entity_map.csv`, `correlation_hits = 0` on a case — the code is ready, the *link* is
  missing. Within-domain analysis (bank money-flow, crypto rings, CDR network, per-entity
  risk) always works. Supply KYC mapping or rely on VPA overlap to light up FR-9.
- **Bank data in PDF/Word** (many statements, in English + Gujarati) is **not parsed** —
  narrative/scanned PDF table extraction and .doc/.docx are out of the current structured
  scope. XLSX/XLS/CSV statements are parsed.
- **High reject counts** (rows from unmapped bank/CDR vendor variants, empty templates,
  junk rows) are expected given the heterogeneity; the primary structured sources are
  captured. Add a profile under `config/profiles/<group>/` to cover a new layout — no code
  change needed.
- **IPDR without MSISDN**: the IP-range IPDR sheets don't include the subscriber number, so
  those sessions attach to the IP (not a phone) and don't fuse with CDR.
- **IMEI/IMSI from CDR are attributes, not merge keys** — in operator CDR they belong to the
  report's target subscriber, not each row's A-party, so merging on them collapses unrelated
  numbers (was caught by the C3 circuit breaker). Phone-number linkage is used instead.
