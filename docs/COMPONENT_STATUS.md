# Component status — what works, what was decided, what still needs work

**As of:** 30 Jul 2026, measured on `FIR 65-2024` and `FIR-0006-2025 U`.
**Reproduce:** `python -m scripts.measure_ingestion --input "<case>"`
**Legend:** 🟢 working and verified · 🔵 decided and deliberately closed · 🟡 needs work ·
🔴 blocked on something outside the code · ⚪ needs a decision from the project owner

---

## 1. Ingestion — readers

| Component | Status | Evidence |
|---|---|---|
| `detector.py` — format by magic bytes | 🟢 | Extensions lie constantly in case material; bytes decide. Catches `.xls` that is xlsx, `.xlsx` that is an AppleDouble stub, `.xls` that is a text report |
| `parsers/excel.py` | 🟢 | Reads every sheet, keeps the best-matching one. Reading only sheet 1 lost data |
| `parsers/tabular.py` (CSV/TXT) | 🟢 | Preamble skip, duplicate-label de-collision |
| `parsers/pdf.py` | 🟢 | pdfplumber; **text-layer decision** replaces the blunt size cap |
| `parsers/docx_tables.py` | 🟢 | All tables, not just the first — a single grid dropped 47% of rows |
| `parsers/fixed_width.py` | 🟢 **new** | Printed statements with no delimiter. Two layouts: HDFC-style headerless, and Bank of Baroda ledger reports. **0 → 743 events** across both cases (73 + 670) |
| `parsers/html_tables.py` | 🟢 **new** | Google legal-process exports. **IP_SESSION 69 → 4,133** |
| `parsers/archive.py` | 🟢 | 3-level recursion, 512 MB budget, path-escape refusal; **every loss now reported** |
| `structure.py` — geometry recovery | 🟢 **new** | Broken PDF grids. Complaint folder 14 → 389 events |
| `value_typer.py` — value-based typing | 🔵 | Works, but **+23 events measured**. Kept as the only way to map a headerless statement or recovered region. **Decision: stop investing** |

## 2. Ingestion — coverage decisions

| Item | Status | Decision and evidence |
|---|---|---|
| `.doc` (40 files) | 🔵 | All 40 verified genuine OLE2 by magic bytes — none mislabelled, so no cheap win. Contents are narrative police paperwork (case diaries, I4C mail, press notes, look-out notices, remand reports). **No financial tables.** Low value |
| `.xml` (19 files) | 🔵 | Response manifests naming a PDF, not data. Correctly skipped |
| Images / media (~2,100) | 🔵 | Recorded, not silently dropped. Mostly WhatsApp chat media inside archives |
| Scanned KYC/AOF (~258 + 14 PDFs) | 🔵 | **OCR closed** — see §6 |
| Reference / roster tables (~4,000 rows) | 🔵 | Correctly refused: no timestamps, no transactions. The paths that would "recover" them fabricate identity links |
| `.vcf` (57 cards) | 🔵 | 45 name↔phone pairs, but **name is not a merge key** → zero FR-9 impact. Attribution value only. Deferred |

## 3. Normalization

| Component | Status | Evidence |
|---|---|---|
| `field_mapper.py` | 🟢 | Non-empty beats empty, first-declared alias wins. Fixed `pstd_dt` overwriting `Tran_Date` |
| `normalizers` — timestamps | 🟢 | IST canonical; SAS `11DEC2019:09:07:02`, NCRP `HR:/MIN:/AM-PM`, time-only hazard closed |
| `normalizers` — phone / amount / account | 🟢 | E.164, quote-stripping, `-:` prefix cleaning |
| **Indic numerals** | 🟢 **fixed 31 Jul** | `\d` is Unicode-aware, so Gujarati ૦-૯ passed every digit test and was never converted. See §3.1 |
| **`Rs.` prefixed amounts** | 🟢 **fixed 31 Jul** | `Rs.75,00,000` returned **0.75**. See §3.1 |
| Dr/Cr orientation | 🟢 | Follows the **balance delta**, not column order. Decided alphabetically it inverted every direction in one file |
| `validation.check_balances` | 🟢 | 31 accounts with ledger breaks flagged on FIR 65-2024 |
| Duplicate event dedupe | 🟢 | Keys on the full session tuple; collapsing concurrent IP sessions was losing evidence |

### 3.1 Gujarati was never deliberately handled — audit of 31 Jul 🔴→🟢

**73% of the files in `FIR-0006-2025 U`** carry Gujarati in their path (921 of 1,268), including
342 PDFs, 114 xlsx and 110 csv; on `FIR 65-2024` it is 126 of 646. No part of the pipeline had
ever been tested against the script. Two defects, one of them severe:

| Defect | Why it was invisible |
|---|---|
| `phone()`, `account_no()` and the column typer's `_digits` **kept non-ASCII digits** | `\d` in a `str` pattern is Unicode-aware, so `re.sub(r"\D", "", …)` treats ૦-૯ as digits and *keeps* them. Every "is this a digit" test passed while the value was never converted, and `phone()` returned `+91૯૮૭૬૫૪૩૨૧૦` — well-formed-looking E.164 that can never compare equal to its ASCII twin |
| `amount("Rs.75,00,000")` returned **0.75** | The dot belonging to `Rs.` survived the character filter while the grouping commas did not, leaving `.7500000`, which `float()` reads as a fraction |

**PHONE, ACCOUNT_NO and IMEI are all merge keys.** So one person written both ways became two
entities and the link was simply absent — no reject entry, nothing to read. A missed identity link
must not be quieter than a fabricated one, which is what rule 3 exists to police in the other
direction. The amount defect is worse still: a ₹75-lakh transfer recorded as **75 paise**,
silently, feeding `total_in`, the `structuring` band test, `layering`'s minimum-amount floor, the
risk score and the STR alike. It is **not Gujarati-specific** — Latin `Rs.` did exactly the same —
but it surfaced only because the police documents write `રૂ.૭૫,૦૦,૦૦૦/-`. The `/-` variant failed
loudly and returned None; the bare `Rs.` form did not.

Fixed with one shared `core.text.ascii_digits` covering nine Indian scripts plus Arabic-Indic and
fullwidth digits, enumerated by block so an auditor can read which scripts are accepted rather
than trusting a Unicode category scan. `value_typer` had its **own** copy of `_digits`, which is
how half the fix got missed the first time — both layers now resolve to the shared function, and
a test asserts they are the same object.

`_luhn_ok` was computing `ord(ch) - 48` across non-ASCII codepoints, so `_is_imei` and `_is_amount`
had been *accepting* Gujarati columns purely because their remaining tests are length-based —
right answer for the wrong reason, with a checksum derived from nonsense.

**Measured effect: +1 transaction on `FIR-0006-2025 U`, and nothing at all on `fir-65-2024`**
(events 247,492 in both arms). high 2 → 2, top score 85.5 → 85.5, 0 band changes, 0 rule-set
changes.

So: correct fixes, one row of yield. Stated plainly because the size of the audit does not justify
itself by its result. The reason is measured, not assumed — **the structured bank data is written
in ASCII.** Across the 18 account-and-mobile tables in the police paperwork, **47 distinct accounts
and 56 distinct mobiles, and not one of them is in Gujarati digits.** The Gujarati numerals appear
in narrative prose and in amounts, not in the identifier columns that feed merge keys.

They are not absent from the corpus, though: across the wider document class there are roughly
**60 MSISDNs written in Gujarati numerals** (§4.2), each one a phone nothing could match before
this fix. They are unreachable for a *different* reason — the documents holding them are not
mapped at all — so the fix is a precondition for that work rather than a beneficiary of it.

The value that remains is latent rather than realised, and it is worth keeping for two reasons.
The `Rs.` amount defect is **not script-specific** and would silently divide any dataset written
that way by 10⁷ — the next case folder is a different police station with different conventions.
And a merge key that silently accepts a non-ASCII digit fails by *splitting an identity*, which
produces no reject entry and no visible symptom; it would have been found only by someone
wondering why two entities looked like the same person.

The identifier columns being blocked is a **separate** problem: those tables carry Gujarati
*headers*, so no profile claims them at all. See §4.1.

## 4. Entity resolution

| Component | Status | Evidence |
|---|---|---|
| `resolve` / `assign_entities` | 🟢 | 6,681 core entities on FIR 65-2024 (was 4,132) |
| Merge keys `PHONE / ACCOUNT_NO / IMEI / IMSI` | 🔵 | **Decision: not extending to AADHAAR / PAN / GSTIN.** Simulated: 5 anchored Aadhaar, 30 PAN, 1 GSTIN in text sources → **1 entity merged**. Not worth three identifier types plus a PII policy |
| Officer-phone veto (`has_admin_role_columns`) | 🟢 | 94 of 98 officers have one mobile vs 10 of 32 accounts. Prevents merging mule accounts into police entities |
| Oversized-component circuit breaker | 🟢 | Fired correctly on `E03390` (3,045 identifiers, hub `PHONE +919702000558`) |
| `account+phone = 3` | 🟡 **see §4.1** | The low number is the officer-phone guard working. But **61 genuine account↔mobile pairs sit in the case folders unread**, blocked by Gujarati headers — 15 of them usable, all three safety checks passed |

### 4.1 The FR-9 bridge is already in the evidence, behind a Gujarati header ⚪

FR-9 has been the only red on the scorecard since the start: STRONG correlation needs one entity
holding both a transaction and a call, and both cases have hundreds of thousands of each — with no
evidence tying an account to a handset. `account+phone = 3`. The recorded next step has been *"the
narrowest unblock is five KYC rows from the case officer"*.

Those rows do not need to be requested. **They are in the case folder**, in `.docx` tables with a
stable five-column schema that recurs across both cases:

| `અ.નં.` | `બેંક એકાઉન્ટ નંબર` | `એકાઉન્ટ ધારકનું નામ સરનામુ` | `રજીસ્ટર મોબાઇલ નંબર` | `રજીસ્ટર ઇ-મેઇલ આઇડી` |
|---|---|---|---|---|
| s.no | **bank account number** | account holder name + address | **registered mobile number** | registered e-mail id |

Measured across both cases, **deduplicated** (`probe_bridge_checks.py`, read-only):

| | tables | distinct accounts | distinct mobiles | distinct pairs |
|---|---|---|---|---|
| `fir-65-2024` | 8 | 29 | 33 | — |
| `FIR-0006-2025 U` | 10 | 18 | 23 | — |
| **both, combined** | **18** | **47** | **56** | **61** |

**Correction to a figure quoted earlier in this work:** "522 account numbers and 223 mobile
numbers" were *occurrence counts of digit runs anywhere in the row* — including IFSC codes,
addresses and the digits inside e-mail addresses — and the same tables are duplicated across
several `.docx` copies. Extracting from the account and mobile **columns** and deduplicating gives
**47 accounts and 56 mobiles in 61 pairs**. An order of magnitude smaller. Still material against
an `account+phone` count of 3, but the honest number is 61, not 303.

All values are **ASCII** — 0 in Gujarati digits — so the numeral work in §3.1 does not reach them.
The single blocker is that `field_mapper` matches English aliases, so a table headed
`બેંક એકાઉન્ટ નંબર` scores zero against every profile and lands in the unrecognised pile.

**Check 1 — officer contamination: PASSES.** Across both cases the admin-role guard identifies
**299 tables** carrying officer/handler columns, holding **1,449 distinct officer mobiles**. Of the
56 bridge mobiles, **0 appear among them.** This is the exact check that disqualified
`master - Copy.xlsx`, and this batch is clean.

**Check 2 — cardinality: PASSES, with the right shape.** Real KYC is near one-to-one:

| | 1 | 2 | 3 |
|---|---|---|---|
| mobiles per account | **36** | 8 | 3 |
| accounts per mobile | **51** | 5 | — |

36 of 61 pairs are strictly one-to-one; the worst fan-out is 3. Contrast the rejected officer
table, where 94 of 98 officers had exactly one mobile but only **10 of 32 accounts** did — the
signature of a shared contact column. Here it is inverted, which is the holder signature.

**Why this is the right kind of evidence, and why it is not being acted on unilaterally.** These
are *bank replies* to a legal-process request: the bank stating which mobile is registered against
which account. That is KYC of the strongest available provenance, and precisely the class the
`entity_map` link mechanism was built to consume — the reader and the link-event path already
exist. It is not the affidavit's narrative allegation, which would be a different and weaker thing.

But it creates identity links, and that is the one area where this project has already come closest
to a serious error: a reference table was very nearly used to merge 32 mule accounts into ~98
police entities, caught only by measuring that its `Mobile Number` column held the *investigating
officer's* number. So three checks were run before proposing any merge. **All three pass.**

**Check 3 — does it actually unblock FR-9?** A bridge only helps if merging the two sides produces
an entity holding a transaction *and* a call *and* an IP session, which is the STRONG precondition
that has been unsatisfiable at every window from 1 to 60 minutes. Measured per pair against
`run_base` output (`probe_bridge_effect.py`):

| | `fir-65-2024` | `FIR-0006-2025 U` |
|---|---|---|
| pairs with both sides resolved | 8 | 7 |
| already the same entity | **0** | **0** |
| would merge two distinct entities | 8 | 7 |
| merge yields TRANSACTION + CALL | 7 | 7 |
| **merge yields TRANSACTION + CALL + IP** | **4** | **0** |

`already_same_entity = 0` in both cases: not one of these pairs is redundant with what the pipeline
already knows. Every usable pair is new information, and 15 links against a current `account+phone`
count of **3** is a fivefold increase in the scarcest link type in the model.

**The honest limit on the 4.** Holding all three event types is *necessary but not sufficient* for a
STRONG hit — the three events must also fall inside the correlation window. **4 is an upper bound on
new STRONG candidates, not a prediction of 4 hits**, and the window sweep already showed the timing
here is tight (MEDIUM only reaches 6 as W widens to 60). The next measurement is the sweep re-run
with the links applied; anything claimed before that is a guess.

`FIR-0006-2025 U` yields **0** for a reason already on record rather than a failure of the bridge:
that case carries no telecom IPDR at all, and its 202 IP sessions are all Google legal-process HTML.
With almost no IP evidence, no merge can produce the third leg.

This is FR-9, the flagship and the only remaining red, and a wrong merge here fabricates an identity
link — rule 3 — in the requirement most likely to be relied on.

### 4.1.1 Built, measured — and it does **not** unblock FR-9 🔴

`entity_resolution/bank_reply_links.py`, behind `ERAKSHAK_BANK_REPLY_LINKS` so both arms of the
sweep run one build. On `fir-65-2024` it loads **35 links, 29 accounts, 33 phones, max fan-out
2/2** — inside the `_MAX_FANOUT` guard of 4.

Window sweep, flag as the only variable:

| W | STRONG off | STRONG **on** | MEDIUM off | MEDIUM **on** |
|---|---|---|---|---|
| 1 | 0 | **0** | 0 | **2** |
| 5 | 0 | **0** | 0 | **4** |
| 10 | 0 | **0** | 2 | **6** |
| 30 | 0 | **0** | 4 | **9** |
| 60 | 0 | **0** | 6 | **11** |

`account+phone` entities **2 → 30**. `high_risk` 0 in both arms; `top_risk` 54.2 → 54.3.

**STRONG stays 0 at every window. The predicted "up to 4" realised as 0.** That was labelled an
upper bound rather than a prediction when it was recorded, and it is worth being explicit that the
bound was loose: holding all three event *types* turned out to say almost nothing about whether the
three fall within 60 minutes of each other. In none of the 4 do they.

**What the links did achieve, and it is not nothing.** MEDIUM nearly doubles, and for the first time
fires at **W=1 and W=5** — a call and a transaction on the same entity within *one minute*, where
previously nothing fired below W=10. That is the tightest temporal coincidence this case has
produced, and `call_transfer_coincidence` now reaches the risk model on MEDIUM (§6.1), so these
become visible findings rather than a statistic.

**The diagnosis this corrects.** FR-9's recorded cause was *"the missing leg is the transaction, i.e.
the account↔phone bridge"*. The bridge is now supplied, and the call+transaction coincidences duly
appear — so **that was the wrong leg.** The blocker is the **IP session**: this case holds 4,133 IP
sessions against 203,050 calls, about 2%, and only 7 entities hold a call and an IP session at all.
The narrowest unblock for FR-9 is therefore **more IPDR coverage, not more KYC** — a materially
different ask of the case officer than the one on record, and one no amount of parsing can satisfy.

### 4.2 The Gujarati police documents, explored as a class ⚪

150 `.docx` documents across both cases, classified by their **own text** rather than by filename
(staging mangles Gujarati filenames into `એફ_ડ_વ_ટ`). Corrected identifier totals — an earlier pass
reported `IMSI: 0`, which was a probe artefact: the label regex allowed only ASCII between `IMSI`
and the digits, and these documents write `IMSI નં. 404…`.

| Table form | tables | What it is | Reachable today |
|---|---|---|---|
| **2 columns, 10+ rows** | **8** (378 rows) | Key-value statutory forms. **Six are the same 53-row bail affidavit template, one per accused** | 🔴 read as a table whose "header row" is a question and its answer |
| 3+ columns | 435 | Record tables — the bank replies of §4.1, seized-property schedules, cheque-book lists | 🟡 partially; Gujarati headers block the rest |
| 1 column | 19 | Layout | n/a |

**36 of the 150 documents carry their evidence in prose only** — no tables at all — so a table
reader cannot see them whatever the headers say. Between them the prose holds 103 IFSC codes, 98
MSISDNs, 88 UPI IDs and 483 Gujarati-numeral amounts in the `notice_yadi` class alone.

Across the whole class: **33 distinct IMEIs**, 1 IMSI, roughly **60 MSISDNs written in Gujarati
numerals** (which §3.1 can now normalise, and which nothing could match before), and **300+
explicit `(SECOND LAYER)` / `(THIRD LAYER)` annotations** — the investigating officer's own
layering determination, written beside the account it applies to.

**The 53-row affidavit is a key-value form, not a record table.** Confirmed by structure: one
affidavit is a single 53×2 table holding **16,526 characters against 939 in its paragraphs**. Each
row is `(૧) label | value`, numbered (૧) through (૪૧), and the values are prose with identifiers
embedded — *"Kalupur A/C 04310112135 is in the name of the applicant/accused …"*, alongside seized
SIM, debit-card, cheque-book and handset schedules that pair an accused with an IMEI and an MSISDN.

Nothing in the pipeline reads a vertical key-value layout from a Word table. The closest existing
machinery is `structure.document_preamble` / `_promote_embedded_fields`, which does exactly this for
PDF header blocks — so the shape is precedented, but the reader does not exist.

**Recommendation, and it is deliberately not what the size of the prize suggests.** These documents
are the officer's *narrative case theory*: an allegation in a legal filing, not a bank's record.
Their provenance is categorically weaker than the §4.1 bank replies, and feeding them into
`node_to_entity` would let an assertion become a merge — which is what rule 3 forbids, and the
precise failure the officer-phone veto exists to prevent. The defensible use is:

1. **Index them for search (FR-15)**, so an analyst asking "which document mentions this account"
   gets an answer. High value, zero identity risk, no new merge keys.
2. **Surface the layer annotations as attributed context** on an entity — *"asserted THIRD LAYER in
   \<document\>"* — never as a derived finding.
3. **Do not merge identities from them.** The §4.1 bank replies are the right source for that, and
   they have now passed both safety checks.

Sizing note for (1): 36 prose-only documents plus 8 key-value forms is the whole seam — 44
documents. That is small enough to be worth doing well and too small to justify a general-purpose
Gujarati NLP layer.

## 5. Correlation

| Component | Status | Evidence |
|---|---|---|
| `timeline_builder` | 🟢 | Per-entity, bisect-indexed. Uses **primary** semantics |
| `window_correlator` | 🟢 | Uses **participant** semantics (primary ∪ counterparty), documented and intentional |
| STRONG / MEDIUM tiers | 🟢 | Only these two exist in code; there is no WEAK tier |
| **STRONG = 0** | 🔴 | **0 at every window from 1 to 60 min** — not a calibration problem. 7 entities now hold CALL+IP; the missing leg is the transaction, needing a real account↔phone link |
| timeline vs correlator semantics | 🟡 | Inconsistent. `correlate` works around it by re-deriving transactions at `window_correlator.py:86`. Documented, not changed |

## 6. Detection and risk

| Component | Status | Evidence |
|---|---|---|
| 6 rules on `demo` | 🟢 | Fire as designed. Scenario-level recall **15/15** |
| — cause 2: `features` was primary-only | 🟢 **fixed** | Counterparty entities now carry fan-in and transfer-derived flows. `mule_account` eligibility on `demo` 30 → 64 entities |
| MEDIUM hits never reached the risk model | 🟢 **fixed** | Both tiers reach `detect`. `call_transfer_coincidence` on `demo` fires 9 → 30, entity-level recall **0.500 → 1.000**; on `fir-65-2024` **0 → 2** |
| MEDIUM weighted below STRONG | 🟢 | `medium_weight: 0.075` vs `0.15`. A call+transfer pair with no IP corroboration is weaker evidence. See §6.1 |
| ML fit population | 🟢 **regression caught pre-merge** | See §6.2 — the counterparty fix had silently moved every observed entity's score by up to 12.4 points |
| `ml_score = 0.0` was ambiguous | 🟢 | New `ml_scored` flag. Min-max normalisation also hands 0.0 to the least anomalous *fitted* entity, so "not anomalous" and "never examined" read identically without it. Closes gap D5 |
| Per-rule eligibility | 🟢 | Was `len(feats)` for 5 of 8 rules. See §6.4 |
| Score saturation | 🟡 preventive | Enabled weights sum to **1.2** against a rule component capped at **1.0**. `typologies_fired` / `rule_weight_raw` / `rule_component_saturated` added, and made ranking tiebreaks. **No entity on either fixture actually exceeds 1.0** — max is exactly 1.0, 0 saturated — so this is diagnostic, not a mis-ranking that was observed |
| `layering` / `circular_flow` | 🟢 | Read `transfers`, which already carried counterparty flows — unaffected by the above |
| `high_risk_entities = 0` on real data | 🟢 **explained, not a defect** | Cause 1 (FATF thresholds) was withdrawn on evidence: `FIR-0006-2025 U` reaches **2 high-risk entities and a top score of 85.5** on the identical unrescaled config (§6.3). §6.4 now says per rule why the remainder is a property of the evidence |

### 6.1 Firing on MEDIUM: what it bought and what it cost

Entity-level, on `demo`, for `call_transfer_coincidence` alone:

| | fired | TP | FP | precision | recall |
|---|---|---|---|---|---|
| STRONG only (before) | 9 | 3 | 6 | 0.333 | **0.500** |
| both tiers (now) | 30 | 6 | 24 | **0.200** | **1.000** |

Recall doubled because a coincidence has two ends and STRONG only caught one. Precision 0.200
sits between the two accepted rules either side of it — `layering` 0.195, `rapid_in_out` 0.107
— so it is not an outlier in this system. And MEDIUM is the **only** tier that occurs on either
real case: STRONG is 0 on both, so without this the rule was structurally dead on real evidence.

Honest limit: 30 of 30 eligible entities fire it on `demo`. With 1,443 calls and 2,736
transactions over 30 entities, a call within 10 minutes of a transaction is near-certain, so on
this fixture the rule carries almost no discriminating power. On `fir-65-2024` it is highly
selective — 6 eligible, 2 fired. The tier weight is the response to that, not a threshold.

Also honest: halving the weight did **not** change which entities change band. The same three
cross into medium either way (from 37.3 / 38.9 / 39.8), and each already held three other
typologies, so MEDIUM was their fourth signal and not their only one. The halving sizes the
contribution to the strength of the evidence; it does not suppress promotions.

### 6.2 The regression the counterparty fix introduced 🔴→🟢

`features.build` gives a feature vector to any entity named in a transfer. That is right for the
rules — fan-in is real evidence about a payee — and wrong for the ML arm, which was silently
refit over the enlarged population:

| | before | after the counterparty fix |
|---|---|---|
| entities in the Isolation Forest fit | 30 | **104** (74 of them counterparty-only) |

Each of the 74 carries a vector whose one non-zero cell is a transfer-derived credit, so the
forest's definition of *normal* became "a counterparty with one credit and nothing else" — and a
real account holder, with calls, sessions and hundreds of transactions, became an outlier **by
construction rather than by behaviour**. Measured cost, before the restriction was put back:

- **29 of 30** observed entities moved by more than 0.05
- mean |Δml| **0.252**, max **0.414**
- at `ml_weight` 0.30 that is **7.6 risk-score points on average, 12.4 at worst**, against a
  high band that begins at 70 — caused entirely by who else was in the fit

Fixed by fitting on entities with records of their own and returning 0.0 for the rest, which is
what they received before they had vectors at all. Verified by A/B against `a7709fe` on the same
dataset: **`ml moved: 0 of 89`**, and every remaining score move is exactly `0.7 × 0.075 × 100 =
5.3` — one rule's tier weight, fully attributable.

Guarded by `backend/tests/test_ml_fit_population.py`. One of those tests initially failed at
`1.0 → 0.998`: the extra edges had been routed *through* the observed entities, changing their
own `fan_out`, which is one of the thirteen ML features. That is a legitimate reason for a score
to move. The invariant is narrower than it first looked — **your own evidence may move your
score, other people's may not** — and the test now says so.

### 6.3 Real-case A/B, code as the only variable

Both arms run the same staged path (`datasets/raw/…`) so nothing but the build differs — see the
`files` trap in `PS_COMPLIANCE_AND_FIX_PLAN.md` §7.11 for why the path must be held fixed.

`fir-65-2024`, W=10:

| | baseline `a7709fe` | fixed |
|---|---|---|
| files / events / transactions / calls / ip_sessions | 961 / 247,492 / 40,309 / 203,050 / 4,133 | **identical** |
| entities / transfers | 7,358 / 14,217 | **identical** |
| flagged entities | 119 | **119** |
| band changes | — | **0** |
| high / medium / low | 0 / 26 / 7,332 | 0 / 26 / **9,970** |
| `top_risk_score` | **54.3** | **54.2** |
| ML fit population | 7,358 | **7,358** |

Exactly **two** entities gain a rule, both `call_transfer_coincidence` from this case's two
MEDIUM hits — the intended fix, and nothing else. `low` grows by 2,638 because counterparty-only
entities now receive a rules-only row instead of no row at all.

The baseline's **54.3 is precisely the figure already recorded** for this case across the whole
FR-9 window sweep — the independent check that the harness measures what the pipeline reports.
The code moves it to 54.2, *down* 0.1. ML scores shift for 3,171 of 7,358 entities but by a mean
of **0.001** and a max of 0.079, i.e. **2.4 risk points at worst**: the fit population is
unchanged, and only the vectors of *observed* entities holding no transactions of their own
gained transfer-derived flows. That mechanism is pinned by
`test_an_observed_entity_with_no_transactions_is_also_filled`.

`FIR-0006-2025 U`, W=10 — 1,305 files, 456,327 events, 343,951 transactions, **112,174 calls
(the documented invariant, unchanged)**, 202 IP sessions, 64,931 transfers in both arms:

| | baseline `a7709fe` | fixed |
|---|---|---|
| high / medium / low | 2 / 42 / 5,430 | 2 / 44 / **24,887** |
| `top_risk_score` | **85.2** | **85.5** |
| flagged entities | 179 | **191** |
| `structuring` fired | 9 | **23** |
| ML fit population | 5,363 | **5,363** |

**`high_risk_entities` stays at 2** — E00012 on five typologies and E00009 on four, both entities
the case holds records for — so the conclusion that withdrew F1's calibration half survives
unchanged. This case has **0** MEDIUM hits, so D1 and D2 cannot reach it at all.

**The unpredicted result: `structuring` fired 9 → 23** — and **10 of those 14 additions were
wrong**, which only became visible when the rule was made to honour its own window. See §6.6.
The corrected figure is **13 fired: the original 9, plus 4 counterparty accounts** that received
three or more INR credits in [₹9L, ₹10L) *inside 24 hours*.

Those 4 are the accounts money was structured *into*, reached from the payer's side — the kind of
subject the counterparty fix was built for, and `mule_account` was the wrong rule to expect it
from. Each carries `ml_scored = false` and a rules-only score, which is the honest presentation:
real evidence about the money, no behavioural profile of the account holder.

**What this cost, stated plainly.** The 14 was written up as a win before the rule it depended on
had been checked. It was inflated 3.5× by a defect that predated this work, and the correction
came from reading the config against the code rather than from any test. A new finding must be
validated against the rule that produced it, not just against the run that produced it.

Two entities change band, **both at the boundary**: E00007 39.9 → 40.0 and E00021 39.7 → 40.6,
on ML shifts of 0.004 and 0.029 — 0.1 and 0.9 risk points. Their rule sets are identical in both
arms. That is a statement about how brittle a hard band edge is for an entity already sitting on
it, not about this change. Worst ML shift anywhere on this case is 0.159, i.e. **4.8 risk
points**.

That 4.8 is **not** comparable to the 12.4 in §6.2: 12.4 was measured on `demo`, and quoting the
two side by side reads as a before/after on one case when it is two numbers from two datasets.
The like-for-like statement is that on this case the fit population is **unchanged at 5,363** in
both arms, so none of the 4.8 comes from the D3 mechanism §6.2 describes — it comes from observed
entities holding no transactions of their own gaining transfer-derived flows, which changes their
own vectors and therefore the fit.

The `structuring` result still corrects §6.1's framing — the counterparty fix was justified there
on `mule_account` eligibility, which turned out not to be where its value was — but the yield is
**4 structuring subjects on live evidence, not 14**.

### 6.6 Three thresholds declared in config and not honoured 🔴→🟢

Found by auditing every key in `config/scoring_rules.yaml` against the code that should read it,
prompted by asking whether the 14 structuring hits above were real. They were not, and the reason
predated all of this work.

| Key | What it did | What it does now |
|---|---|---|
| `structuring.window_hours: 24` | **Never read.** The timestamp was discarded at `for (_t, a, asset) in f["credits"]`, so *every* in-band credit in the case counted however far apart — three ₹9.5-lakh receipts years apart read as smurfing | Sliding window; the flag names the burst count *and* the wider in-band total, so the broader context is not lost |
| `rapid_in_out.max_hold_minutes: 60` | Read **only to build the flag text**. The measurement came from one precomputed scalar fixed at 120, so every flag asserted "forwarded within 60min" about a computation that had allowed 120 | Each rule computes its own window. `mule_account` keeps 120, `rapid_in_out` gets the 60 it asks for |
| `call_transfer_coincidence.window_minutes: 10` | Read by **nothing**. The window is applied upstream in correlation, so editing it here changed nothing | Removed, with the reason and the real setting recorded in its place |

The middle one is the worst of the three and the only one that was wrong *on the page*: a forensic
report is a document someone relies on, and it was stating a window that had not been measured.
Structuring merely over-fired; `rapid_in_out` made a false assertion about its own evidence.

Measured effect:

| | `demo` | `FIR-0006-2025 U` | `fir-65-2024` |
|---|---|---|---|
| `structuring` fired | 3 → **3**, precision **1.000**, recall **1.000** | 23 → **13** | 0 → **0** (nothing in the band) |
| `rapid_in_out` fired | 28 → **23**, precision 0.107 → **0.130**, recall **1.000** | 58 → **58** | 21 → **21** |
| entities whose rule set changed | 5 | 10 | **0** |
| high / top score | 3 high | 2 high, 85.5 | 0 high, 54.2 — **all unchanged** |

On `demo` this is strictly better: `structuring` keeps all three planted scenarios with **zero**
false positives, and narrowing `rapid_in_out` to the 60 minutes it advertises removes **five**
false positives while keeping all three true ones. Overall scenario recall stays **15/15**.

On `FIR-0006-2025 U` the 10 dropped `structuring` flags were **all** counterparty-derived, and
**all 9 firings that predate the counterparty fix survive untouched** — so the window fix removed
exactly the artefacts the fill had introduced and nothing that was already there. `rapid_in_out`
loses nothing, because real UPI/IMPS forwarding on this case is already well inside 60 minutes.

On `fir-65-2024` **nothing moves at all** — not one entity's rule set, band, or score. `structuring`
was already 0 eligible there (no transaction anywhere in [₹9L, ₹10L); the case maximum is ₹70L),
and every `rapid_in_out` forward was already inside 60 minutes. A correctness fix that changes
nothing on one of two real cases is the expected shape when the defect needed a specific data
pattern to bite.

`test_rule_windows.py` pins each window against a credit placed just inside and just outside it,
and closes the class of defect with a test that reads the YAML and fails if **any** declared
threshold is not referenced by the rule that declares it.

### 6.4 Eligibility was an entity count wearing a diagnosis

`eligible` fell back to `len(feats)` for five of the eight rules, so on `fir-65-2024`
`mule_account` reported **9,996 eligible, 0 fired** — which reads as a broken detector. It is now
each rule's structural precondition, before its threshold applies:

| rule | eligible now means | `fir-65-2024` before → after | fired |
|---|---|---|---|
| `mule_account` | reaches `min_fan_in` | 9,996 → **6** | 0 |
| `rapid_in_out` | seen both receiving *and* sending | 9,996 → **35** | 21 |
| `call_transfer_coincidence` | holds both a call and a transaction | 9,996 → **6** | 2 |
| `comm_burst` | has call records | 9,996 → **3,991** | 30 |
| `dormant_activation` | has ≥2 transactions to measure between | 9,996 → **454** | 25 |

"6 eligible, 0 fired" is a finding: **only six entities in a 7,358-entity case reach fan-in ≥ 5
at all, and none of them forwards.** And when eligible is 0, a sentence says why — *"no entity is
seen both receiving and sending, so forwarding cannot be observed — a one-hop view of the money
trail."* That is what stops `fired = 0` reading as "nothing suspicious here".

`mule_account` still fires 0 on `fir-65-2024`, and that is **correct behaviour on incomplete
evidence, not a code defect**: a counterparty-only entity here is a *terminal payee* — money in,
never out — because the case holds the victim's statement and not the mule's. `max_rapid_forward`
is 0 by definition. Same shape as FR-9: a missing-data problem wearing a detection problem's
clothes.

## 7. Reject reporting (rule 2: nothing dropped silently)

| Path | Status |
|---|---|
| Row-level mapping failures | 🟢 itemised with a reason |
| Blank / layout rows | 🟢 separated as non-evidentiary (**42,761** on FIR 65-2024) |
| Per-file parse failures | 🟢 reach `Investigation.rejects` |
| Files never opened | 🟢 recorded with a reason, **categorised** so 47 actionable files are not hidden inside 2,571 |
| Over-cap PDFs | 🟢 recorded as `"scanned PDF, no text layer … needs OCR"` |
| PDF parsing disabled | 🟢 recorded |
| Duplicate exhibits | 🟢 parsed once, recorded with `duplicate_of` |
| Archive budget / depth / password / unreadable | 🟢 **all now reject entries.** 534 members unextracted on one archive |
| **Remaining rule-2 gaps** | 🟢 none known |

## 8. Measurement tooling

| Tool | Status | Purpose |
|---|---|---|
| `scripts/measure_ingestion.py` | 🟢 | **Authoritative** ingestion figures; composes rejects exactly as `run_base` does |
| `scripts/census_skipped.py` | 🟢 | Sub-minute pre-flight estimate. **Explicitly not the coverage figure** — one archive level, ignores the budget |
| `scripts/run_pipeline.py` | 🟢 | Full pipeline with `--save` |
| `ERAKSHAK_VALUE_TYPING` / `ERAKSHAK_STRUCTURE_RECOVERY` | 🟢 | Flags so both arms of an A/B run the same build |

---

## 9. Needs work — ranked

Five items from the previous revision are **closed**, and three of the five were closed by
*re-measuring* rather than by engineering — the recorded figure was stale. That is now the
first step for anything on this list.

| # | Item | Size | Why it is not done |
|---|---|---|---|
| 1 | WhatsApp `_chat.txt` | **5,889 rows** — now the single largest recoverable block | ⚪ Blocked on the `MESSAGE` event-type decision, not on code |
| 2 | Detector primary-only semantics | 15,098 entities | ⚪ Needs its own validation baseline — impact already quantified |
| 3 | MEDIUM hits absent from risk model | latent | Small fix, but changes risk output → wants a baseline |
| 4 | F1 threshold calibration | FR-11/12/13 | **Premise weakened — see §9.1.** Needs re-scoping before any gate is touched |
| 5 | Residual "no time anchor" rows | 17,811 rows | Mostly NCRP state rosters that legitimately carry no timestamps, so largely *not* recoverable as events |
| 6 | Residual broken-geometry PDFs | 976 rows | Down from 9,792. Long tail, low value per unit of work |

**Closed since the previous revision:** risk heat map (F5, FR-18 green) · location filter
(F7, FR-15 green) · IPDR row rejects (F6, FR-3 green — figure was stale) · STR content review
(FR-17 green, four defects fixed) · Bank of Baroda ledger layout (**0 → 743 events**).

### 9.1 F1 needs re-scoping, not tuning

F1's premise is that `high_risk_entities = 0` on `FIR 65-2024` means the FATF gates are
mis-calibrated for real money. The first full run of `FIR-0006-2025 U` contradicts that: it
produces **2 high-risk entities and a top score of 85.1 with the identical, unrescaled
scoring**.

So the gates work. `FIR 65-2024` has no entity exhibiting enough typologies, which is a
statement about that case's evidence. Two measured causes of its zero, neither a threshold:

1. that case genuinely lacks the typology coverage — confirmed by a second case reaching 85.1
   on the same config;
2. `detection/features` aggregates by primary entity only, so 15,098 entities holding
   transactions solely as a counterparty carry an empty feature vector at **any** threshold
   (§6).

Rescaling the bands to force a non-zero count on `FIR 65-2024` would have inflated
`FIR-0006-2025 U` and diluted its two genuine highs. Recommendation: replace "calibrate the
thresholds" with the **rule eligibility report** F1 already proposes — per rule, how many
entities were eligible and how many fired — so `eligible=0` and `fired=0` stop looking alike.
That is the part of F1 that is still clearly worth doing.

## 10. Decisions taken, against the problem statement

The problem statement is **ERH26_PS_03 — AI-Powered Financial & Telecom Dataset Analyzer
(Bank, CDR & IPDR Fusion)**, and its 19 requirements are the scope. Each open question was
resolved against that rather than against what the data happens to contain.

### 10.1 `MESSAGE` event type for WhatsApp chat — **REJECTED, out of scope** 🔵

5,889 rows of timestamped chat sit unread, and the temptation is to model them. Against the
problem statement they are not in scope: the fusion named is **Bank, CDR and IPDR**, and no
requirement covers messaging content. Adding a fourth event type would touch the canonical
model, correlation tiers, detection features, the graph and the UI — the largest change in the
system — to serve data the specification does not ask about.

Two narrower alternatives were considered and both rejected on evidence:

- **Map chat onto `CALL`.** Puts false call records into evidence. A message is not a call,
  and CDR-derived call counts feed `comm_burst` and the correlation tiers.
- **Emit chat participants as LINK events.** Worse. `LINK` *merges* identifiers into one
  entity, and two people talking are not one person. This would fuse every participant of a
  group chat into a single entity — the same failure mode as the officer-phone register,
  reached by a different route.

Recorded as a scope decision so it is not re-opened as an oversight. If messaging is ever
added to the specification it needs its own event type and its own validation baseline.

### 10.2 Detector primary-only semantics — **eligibility report first** 🟡

FR-13 (mule-account signatures) is measurably unreachable for 15,098 entities whose
transactions appear only as a counterparty: `E02650` holds 84 transactions, ₹280,700 in and
₹268,508 out with `max_rapid_forward` 1.0, and `mule_account` cannot fire on it. A participant
simulation moves `rapid_in_out` 20 → 120 and `mule_account` 0 → 3.

Flipping the semantics globally is still not the first move, because the **rule eligibility
report** (§10.4) now makes the gap visible in the product rather than only in a probe. Order
matters: publish the audit trail, then change what it audits, so the change is measurable
against something. Flipping first would have altered risk output with no instrument to read it
against — the mistake this project keeps paying for.

### 10.3 512 MB archive expansion budget — **default unchanged** 🔵

It is a zip-bomb guard on untrusted third-party input, not a tuning parameter, and the 534
unextracted members of `WhatsApp Chat - Bhai.zip` are overwhelmingly chat media that §10.1
puts out of scope. It is already configurable as `ingestion.max_archive_mb`, and the
truncation now produces a reject entry naming the member that exhausted it, so an analyst can
raise it deliberately for one case. Visibility was the actual defect; the number was not.

### 10.4 F1 threshold calibration — **calibration withdrawn, eligibility report built** 🟢

See §9.1 for why the calibration half is withdrawn. The eligibility report existed in
`rules.eligibility_report`, fully written and tested, and **nothing ever called it** — the same
shape F3 was in. It now reaches `Investigation.rule_eligibility`,
`GET /v1/rule-eligibility/{ds}`, and section 6 of the forensic report.

### 10.5 Five KYC rows from the case officer — **made as easy as possible** 🔴

Still the only measured path to FR-9 STRONG, and still not something code can supply.
`datasets/entity_map.template.csv` now carries the five MSISDNs as commented rows with the
reason attached, so the officer fills in one column and deletes a `#`. The loader skips
comments, and a test pins that the commented rows produce no links until they are filled in.

## 11. Blocked on evidence, not code 🔴

**FR-9 STRONG = 0.** Needs verified account↔mobile pairs for five MSISDNs that already have
both call and IP activity:

```
FIR 65-2024     : +919537658408  +919687045370
FIR-0006-2025 U : +919099102222  +919737002222  +919825504222
```

One row each in `entity_map.csv` makes STRONG testable with no new code and no inferred link.
Everything cheaper has been tried and measured: the window is not the problem (0 at 1–60 min),
the scans cannot supply verified pairs (OCR gave 9 of 10 digits with nothing to check it
against), and the one file that looked like the bridge carries the investigating officer's
phone.

---

## 12. Requirement scorecard

**9 green · 9 amber · 1 red.** FR-3 moved red → amber this cycle. FR-9 is the only red, and is
blocked on evidence rather than code. Full detail in `PS_COMPLIANCE_AND_FIX_PLAN.md` §7.

## 13. Headline numbers — `FIR 65-2024`, W=10

| Metric | Before | Now |
|---|---|---|
| Transactions | 35,870 | **39,170** |
| IP sessions | 69 | **4,133** |
| Events | 238,985 | **246,353** |
| Entities | 4,132 | **6,681** |
| `rejected_rows` | 140,040 | **118,836** |
| Rows stranded unrecognised | 23,846 | **16,307** |
| Parse time | 1,043 s | **646 s** |
| Tests | 142 | **215** |

`FIR-0006-2025 U` ingestion: 456,423 events · 344,047 transactions · 202 IP sessions.
Its full-pipeline entity/correlation figures are pending a first run.
