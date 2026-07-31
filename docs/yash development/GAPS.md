# Gaps — what is genuinely unfinished

Ranked by value, sized where a size was measured. A gap with no number beside it has not
been measured, and that is said rather than guessed.

Three categories, and the distinction matters more than the ranking:

- **Blocked on evidence** — no code change helps. Stop working on it.
- **Open engineering** — measurable work with a known target.
- **Blocked on a decision** — the code is straightforward; someone has to choose.

---

## 1. Blocked on evidence — do not spend time here

### FR-9 STRONG correlation = 0 🔴

The flagship requirement. **0 at every window from 1 to 60 minutes.**

The missing leg is the **IP session**, and this was re-diagnosed after being wrong once:

```
ip_sessions            4,133   against 203,050 calls  (~2%)
entities with call+IP       7
account+phone              30   (bridge built, and STRONG still did not move)
```

The bridge was the previous suspect. B built it — 35 links from Gujarati bank KYC replies,
`account+phone` 2 → 30 — and STRONG stayed 0 while MEDIUM nearly doubled and fired at W=1
for the first time. So call+transaction now coincide; the IP leg does not exist to join.

Source-file evidence: the two IPDR MSISDNs, their IMEIs and IMSIs appear in **zero** files
outside `ipdr/`. The second case has no telecom IPDR at all.

**Only unblock:** IPDR covering numbers already present in the CDR. That is an exhibit
request to the case officer, not an engineering task.

**Not an unblock:** the 31 password-protected archive members. All 7 archives are CDR or
IMEI — none is IPDR.

---

## 2. Open engineering — ranked

### 2.1 WhatsApp `_chat.txt` — 5,889 rows ⚪

The single largest recoverable block left. **Blocked on a decision, not code**: there is no
`MESSAGE` event type in the canonical model. Someone has to decide whether chat messages
join the timeline as events, and if so what their entity and counterparty are.

Two WhatsApp archives (990 MB + 326 MB) also exceed the 256 MB upload cap and are excluded
from staging — they are media-heavy, so the text is a small fraction.

### 2.2 Detector primary-only semantics — ~~15,098 entities~~ 🟢 **DONE `6f7751f`**

`features.build` now fills fan-in and money flows for counterparty-only entities. Do not
rebuild this.

It also introduced a regression worth reading before you touch `features.build` again: giving
every transfer counterparty a feature vector silently enlarged the **Isolation Forest fit
population** from 30 to 104 on `demo`, and moved every observed entity's ML score by up to
**12.4 risk points** for reasons unrelated to its own behaviour. The forest is now fitted only
on entities holding records of their own. See `../COMPONENT_STATUS.md` §6.2.

### 2.3 MEDIUM correlation hits absent from the risk model — 🟢 **DONE `6f7751f`**

Both tiers reach `detect()`. MEDIUM carries `medium_weight: 0.075` against STRONG's `0.15`,
because a call+transfer pair with no corroborating IP session is weaker evidence. On `demo`
this took the rule's entity-level recall **0.500 → 1.000** at a precision cost of
0.333 → 0.200; on `fir-65-2024` it fires **2** where it previously fired 0.

Honest note kept from that work: halving the weight suppresses **no** band promotion — the same
three demo entities cross either way. The justification is evidential, not measured.

### 2.4 Residual "no time anchor" rows — 17,811 rows 🟡

Mostly NCRP state rosters that legitimately carry no timestamps. **Largely not recoverable
as events** — they are reference data. Overlaps 3.1 below: the right destination is LINK
events, not timeline events.

### 2.5 Residual broken-geometry PDFs — 976 rows 🟡

Down from 9,792 after structure recovery. Long tail, low value per unit of work. Complaint
PDFs where the table geometry is wrong — `'Under Process 14/07/2024 01:02:01 PM'` bleeding
into column 0 — so the timestamp exists but no amount of column typing reaches it.

### 2.6 Format gate — `.html` and `.xml` still unopened 🟡

`.html` (8 + 15 files) and `.xml` (9 + 6) are near-trivial via `pandas.read_html` / lxml.
Legacy `.doc` (21 + 19) is genuinely awkward: `sniff_container` detects OLE2 but there is no
clean pure-Python reader. Scope `.doc` separately rather than promising it.

These are now at least **counted** rather than invisible.

### 2.7 FR-1 bank parsing still lossy 🟡

140 BANK tables → 39,170 transactions. Recognition is largely fixed (fallback + value
typing); what remains is row-level mapping inside newly-recognised files, which are flagged
`needs_manual_mapping` by design. Re-measure before assuming a fix is needed.

---

## 3. Blocked on a decision

### 3.1 Reference tables carrying account ↔ mobile — 🟢 **DONE `e3a0633`**, and it did *not* unblock FR-9

`master - Copy.xlsx` holds **173 rows with an account number and a mobile number side by
side**. The value gate correctly refuses the file — no timestamp, no transactions, so it is
not a source of events.

But that is the account↔phone bridge material, and `er_mapping.load_link_events` already
accepts exactly this shape. The work: detect a reference table (≥2 merge-key columns, no
time anchor) and emit **LINK events**, which contribute merge edges only — not timeline,
not detection.

**Constraint that cannot be relaxed:** never fabricate a pair. A false account↔phone link
puts an innocent person inside a correlation hit. Only emit a link the table states
explicitly, on the same row.

Note the ordering: 337 tables of this shape are **refused on purpose** on one case. They are
not a parser gap; they need a different destination.

**Built as `entity_resolution/bank_reply_links.py`, on by default.** Source was not
`master - Copy.xlsx` — that file's `Mobile Number` column is the *investigating officer's*, and
linking it would have merged 32 mule accounts into ~98 police entities. The real source is the
Gujarati bank KYC replies in the police paperwork: `બેંક એકાઉન્ટ નંબર` beside
`રજીસ્ટર મોબાઇલ નંબર`. 35 links, `account+phone` **2 → 30**.

Three safety checks were run first and all passed — 0 of 56 bridge mobiles appear among 1,449
officer mobiles; 36 of 61 pairs are strictly one-to-one; and the merge yields call+transaction
on 7 pairs. **STRONG still did not move.** The acceptance criterion in §6 below ("`account+phone`
rises, nothing else moves") was met exactly, and FR-9 stayed red anyway.

### 3.2 `datasets/entity_map.template.csv` is still the 4-line template ⚪

The KYC route to the bridge. Needs real account ↔ registered-mobile pairs from the case
officer. The loader works and is unit-tested — it is one CSV away from taking effect.

Cannot be filled in by an agent. Fabricating entries would manufacture evidence.

### 3.3 OCR for scanned evidence — closed with evidence ⚫

58 TIF/JPG images. Investigated and **closed rather than deferred** — see
`../PARSER_COVERAGE.md` §3.1. Do not reopen without reading that section.

---

## 4. Unverified rather than broken

These are not gaps in the code; nobody has exercised them.

| Item | State |
|---|---|
| **Interactive UI** | `/ask` and `/quality` compile and serve 200. Nobody has typed a question, expanded a QuerySpec panel, or read the reject table in a browser. Given that `_app.quality.tsx` shipped with four type errors, runtime bugs are likely |
| **Gemini on real CDR** | 6/6 questions planned, 1.2–5.1 s each. Not re-run since the timeout fix |
| **`docker build` in CI** | verified locally, cold, no cache. Not confirmed on a CI runner |
| **F1 threshold calibration** | premise weakened — `FIR-0006` reaches 85.1 on the same config. Needs **re-scoping, not tuning** |

---

## 5. What is genuinely finished

So nobody re-opens it. Detail and evidence in `../PS_COMPLIANCE_AND_FIX_PLAN.md` §1.

**11 of 19 requirements green:** CDR parsing · IPDR parsing (zero row rejects, 4,133
sessions) · schema auto-detection (95.6% / 97.8% by rows) · reject diagnostics · timestamp
normalisation · unified timeline · money-flow and comms graphs · filter/search on both paths
· forensic report over HTTP (PDF + DOCX) · STR generation · risk heat maps · NL query.

Three of those went green on 30 Jul by **re-measuring**, not by new code. The recorded
figure was stale. Check the number before you build anything.

---

## 6. If you have one day

Revised 31 Jul. The previous version sent you to build 3.1, which now exists and is on by
default — that is exactly the failure mode this file is meant to prevent, so check the 🟢
markers before starting anything.

1. **Re-measure whatever you are about to fix.** Cheaper than fixing it three times, which has
   now happened. Three requirements went green by re-measuring alone, and **FR-4 was measuring
   tables when it should have been measuring rows** — the gap was twenty times smaller than the
   headline said.
2. **§4 — drive the UI.** Still the cheapest way to find real defects and still never done. It
   is now the highest-value item on this list.
3. **§2.1 WhatsApp**, if and only if someone decides the `MESSAGE` question. It is a decision,
   not code.

Do **not** start with:

- **FR-9 STRONG.** An exhibit request. Every code-side hypothesis has been built and measured;
  each moved the number it should have and none moved STRONG. See §1.
- **FR-4 profiles.** The genuine parser gap across both cases is **3 tables and 92 rows**,
  0.008% of 1.11 M rows parsed. Run `unrecognised_by_reason` before believing otherwise.
- **Widening `common_imei.py`'s filename match.** You will notice it skips 5 of 8
  `Common_*_Report` files and it looks like free coverage. It is not — see `DECISIONS.md`.

### Ground truth for "is it working"

Verified end to end on 31 Jul: **425 tests**, ruff clean, `tsc` clean, `vite build` succeeds;
pipeline runs on `demo` and both real cases; **15 API endpoints, 18/18** including 401
unauthenticated and 400 on a bad report format; PDF and DOCX both generate.

Environment flags you may need:

| flag | default | effect |
|---|---|---|
| `ERAKSHAK_BANK_REPLY_LINKS` | **on** | `=0` restores the pre-bridge baseline for an A/B |
| `ERAKSHAK_VALUE_TYPING` | on | instance-level column typing |
| `ERAKSHAK_STRUCTURE_RECOVERY` | on | broken-grid geometry recovery |
| `ERAKSHAK_PERSIST_MODEL` | off | `=1` to write a fitted forest; otherwise every page view would rewrite the committed artifact |

---

## 7. Added 31 Jul

### 7.1 FR-4 is not a parser gap — the figure was the wrong unit 🟢

"658 of 951 unrecognised" counts **tables**. The unclaimed ones average 24 rows against thousands
in the claimed ones. By rows: **95.6%** claimed on `fir-65-2024`, **97.8%** on `FIR-0006-2025 U`.

`ingestion/unrecognised.py` splits the residue by reason — value-based, not filename-based:

| reason | `fir-65-2024` | `FIR-0006-2025 U` |
|---|---|---|
| `out_of_scope_no_canonical_field` | 482 tbl / **13,315** rows | 640 tbl / 6,330 rows |
| `refused_officer_bearing` | 106 tbl / 787 rows | 337 tbl / **7,332** rows |
| `reference_no_time_anchor` | 83 tbl / 2,078 rows | 94 tbl / 3,102 rows |
| **`unread_parser_gap`** | **0 / 0** | **3 tbl / 92 rows** |

**3 tables and 92 rows across both cases — 0.008% of 1,114,168 rows.** The biggest single unclaimed
table is an 11,275-row **CCTV log**, which is not Bank, CDR or IPDR. The biggest tranche on the other
case is officer-bearing NCCRP registers, refused on purpose.

Caveat: `unread_parser_gap` needs a canonical field **and** a column `value_typer._is_temporal`
recognises, so the 0 is bounded by that date coverage rather than proof of completeness.

### 7.2 FR-1's "lossy" is mostly not loss 🟡

Of 117,741 rejected rows on `fir-65-2024`: **34.6% de-duplicated events**, 0.4% blank layout rows —
neither is a loss — and 13.7% unclaimed tables (see 7.1). The one actionable category,
`row missing timestamp / primary identifier` at 60,325 rows, was **one reason hiding two**, now
split. A row with no timestamp can never be an event; a row that has a time and lost its identifier
is a mapping gap. Those want opposite responses and were indistinguishable.

**Start here if you want FR-1 work**: read the `no mapped primary identifier` count first. That is
the actionable half and nobody has measured how large it is on its own yet.

### 7.3 Narrative paperwork is searchable, and is not identity 🟢

`GET /v1/document-mentions/{ds}?identifier=` over **123 Gujarati police documents** — 469 accounts,
435 phones, 280 IFSC, 20 IMEI, 11 UPI. **39 of them carry their evidence in prose only** and were
invisible to any table reader; 8 are two-column key-value forms, six of those the same 53-row bail
affidavit whose single table holds 16,526 characters against 939 in its paragraphs.

Two constraints are enforced by test. Matching is by **identifier, not substring** — `?identifier=2348`
must not return every affidavit containing that run inside a longer account number. And a record
carries no `own_identifiers`, no `primary`, no `event_type`: **these are pointers into the evidence,
never merge keys.** An affidavit is the officer's allegation; identity comes from the bank replies
only. The `(SECOND LAYER)` tags are carried as `asserted_layers` attributed to the document and are
never an input to the `layering` typology, which derives its own hops from the transfer graph.

### 7.4 Score saturation — instrumented, not observed 🟡

Enabled rule weights sum to **1.2** against a rule component capped at **1.0**, so six typologies and
eight can score identically. `typologies_fired`, `rule_weight_raw` and `rule_component_saturated`
were added as ranking tiebreakers across `/v1/entities`, the heat map and the report.

**No entity on either fixture actually exceeds 1.0** — max is exactly 1.0, 0 saturated. This is
preventive and diagnostic, not a mis-ranking anyone observed. Do not cite it as a fixed bug.

### 7.5 `ml_score = 0.0` was ambiguous 🟢

Min-max normalisation hands `0.0` both to the least anomalous *fitted* entity and to every entity the
forest was never fitted on. `ml_scored` now distinguishes them, in the API, the database and the UI —
"we looked and found nothing unusual" and "there was never anything to look at" are different
findings. Closes gap D5 in `../gap_analysis.md`.
