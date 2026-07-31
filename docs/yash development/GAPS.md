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

### 2.2 Detector primary-only semantics — 15,098 entities 🟡

`detection/features` aggregates by **primary** entity only, so 15,098 entities holding
transactions solely as somebody else's counterparty carry an empty feature vector at *any*
threshold. Impact is quantified; the fix needs its own validation baseline because it moves
every risk score.

This is one of the two measured causes of `high_risk = 0` on `FIR 65-2024`. It is **not** a
threshold problem — see `DECISIONS.md`.

### 2.3 MEDIUM correlation hits absent from the risk model — latent 🟡

Risk scoring is STRONG-only, deliberately, so MEDIUM could not inflate scores when it was
introduced. Now that MEDIUM fires (11 at W=60), a two-leg coincidence contributes nothing to
risk. Small fix; changes risk output, so it wants a baseline first.

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

### 3.1 Reference tables carrying account ↔ mobile 🔴 highest evidential value

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

1. **Re-measure whatever you are about to fix.** It has cost less than fixing three times
   now.
2. **3.1 — reference-table LINK events.** Highest evidential value; attacks the requirement
   that is actually red, and the acceptance criterion is unambiguous (`account+phone` rises,
   nothing else moves).
3. **4 — drive the UI.** Cheapest way to find real defects, and it has never been done.

Do **not** start with FR-9 STRONG. It is an exhibit request.
