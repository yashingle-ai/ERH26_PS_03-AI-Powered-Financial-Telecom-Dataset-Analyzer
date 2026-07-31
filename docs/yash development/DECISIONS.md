# Decisions taken, and why

Every judgement call that a future reader would question, with the measurement that drove
it. Several of these look wrong until you know what was measured — that is exactly why they
are written down.

Two Claude sessions worked this repo concurrently (referred to as **A** and **B**).
Attribution is recorded where it is known and marked unknown where it is not.

---

## Correlation and the flagship requirement

### FR-9 STRONG = 0 is an evidence gap, not a defect — do not reopen

Verified at source-file level, which is stronger than the entity-level check either session
had first:

```
IPDR MSISDNs : 2 subscribers   (values redacted — see note)
IPDR IMEIs   : 2
IPDR IMSIs   : 2

each of the six, searched across cdr/            : 0 files
each of the six, searched anywhere outside ipdr/ : 0 files
```

> **The identifiers are deliberately not written here.** This block carried the live MSISDNs,
> IMEIs and IMSIs, and one of those IMEIs matches a real `IPDR_-_Common_IMEI_Report` exhibit.
> Case evidence must not sit in the repository — the same rule that keeps `datasets/` out of git.
> The argument does not need them: what matters is that **all six appear in zero files outside
> `ipdr/`**. Reproduce with `grep -rl "<identifier>" datasets/raw/<case>/` against the live folder.

Two subscribers have internet records and nothing else. Confirmed independently on the
second case, which has no telecom IPDR at all.

**The diagnosis was then revised, and this is the important part.** The working theory was
that the account↔phone bridge was the blocker. B built it — `bank_reply_links`, 35 links
from Gujarati bank KYC replies, `account+phone` 2 → 30 — and **STRONG stayed 0**. MEDIUM
nearly doubled (6 → 11 at W=60) and fired at W=1 for the first time, proving call and
transaction now coincide. So the missing leg is the **IP session**: 4,133 against 203,050
calls, only 7 entities holding call+IP at all.

The narrowest unblock is **IPDR coverage, not KYC**. A prior version of the docs said the
opposite; it was wrong and has been corrected.

### Tiered correlation: STRONG and MEDIUM, with STRONG unchanged

`correlate()` required all three legs, so 10 entities with both money movement and calls
were discarded and the product reported "0 hits". Added `MEDIUM` (call + transfer, no IP)
as a **separate tier** with its own field.

`correlation_hits` still means STRONG only. `correlation_hits_medium` is new. Rationale: a
stakeholder comparing runs would read a jump in the existing field as FR-9 suddenly
working. Risk scoring stayed STRONG-only.

MEDIUM = 2 was **independently re-derived** — 224k events walked with a separate bisect —
rather than trusting the correlator's own tally.

### Password-protected archives are not a likely unblock

31 encrypted members across 7 archives, and **all 7 are CDR or IMEI — none is IPDR**. So a
password adds call coverage, and can only produce STRONG if an unlocked CDR happens to
contain one of those two MSISDNs. Ask the case officer, but do not imply it will unblock
FR-9.

A locked archive filename contains a number that differs from one of the IPDR MSISDNs **by a
single digit**. It is a different subscriber. Recorded because the near-match was once read as a
lead, and a transposition is exactly the kind of thing that looks like a breakthrough at 2am.
(Identifiers redacted — see the note above.)

---

## Detection and risk

### Risk bands were NOT rescaled, and the second case proved that right

`high_risk_entities = 0` on `FIR 65-2024`. The scoring is
`100 × (0.7 × min(1, Σweights) + 0.3 × ml)`, and the eight rule weights total 1.20, so
"high" (≥70) needs Σweights ≥ 1.0 — essentially every typology on one entity. On that case
only five typologies can occur at all, capping the reachable score at 52.

The tempting fix was to renormalise against the typologies a case *can* express. **Refused.**
It scales scores up on any case with fewer applicable typologies and would label entities
high for exhibiting two things.

**The first full run of `FIR-0006-2025 U` settled it: 2 high-risk entities, top score 85.1,
identical unrescaled scoring.** The gates work. Rescaling would have inflated this case and
diluted its two genuine highs.

What was fixed instead was the *headline*: `risk_bands` and `top_risk_score` were added, so
"0 high" arrives with the context that 25 sat at medium.

### `structuring`'s ₹10 lakh threshold is regulatory, not tunable

It looks for transactions just below ₹10 lakh. Real case p99 is ₹1 lakh, so it fires zero
times. That is India's actual CTR reporting threshold — **"no structuring in this case" is
the correct answer**, and scaling it would have manufactured findings.

Contrast with `layering`/`circular_flow`'s `min_amount_inr: 10000`, which the config itself
calls a noise filter. That one *was* made adaptive (`min(configured, case median)`) because
it sat at the real case's p90 and was excluding 90% of transfers.

**Honest outcome: the adaptive floor delivered nothing measurable.** Eligible transfers rose
to 4,710 and both rules fired 55 and 15 — unchanged. The amount gate was never the
constraint. The change is better-principled and demo stays bit-identical, but it is not
claimed as a win.

### The eligibility report — the part of F1 worth keeping

"0 high-risk entities" reads to an investigator as *nothing suspicious here*. Per rule it
meant different things: `structuring` could not fire at all, `layering` was searching a
tenth of the graph. `eligibility_report()` now gives enabled / eligible / fired / note, so
**a rule that never ran stops looking like a rule that found nothing.**

Same principle as counting rejected rows instead of dropping them.

---

## Ingestion

### A profile may claim a file it can demonstrably map

`match.required_any` and `field_map.aliases` are independent lists that drift. A statement
headed `Trans Date and Time | Transaction Details | Debit | Credit | Balance` mapped six
canonical targets cleanly and scored **0.0**, because `required_any` wanted the literal
string "debit amount".

Patching tokens postpones the problem to the next bank. So when `required_any` finds
nothing, a profile may claim the file if it maps a time anchor, a subject, and ≥3 distinct
targets — at confidence capped **0.49**, below `auto_detect_threshold`, so such a file is
always `needs_manual_mapping` and always outranked by a genuine match. **Inferred is not
asserted.**

`required_all` was moved *ahead* of `required_any` and remains a hard gate: it means "this
shape is mandatory", so no fallback may bypass it. Pinned by a test.

### Value-based column typing (session B)

A column may only claim a canonical target if its **sampled values** look like that type.
Nothing maps on a name alone, because that is the mechanism that already fails. Plus
abbreviation-aware fuzzy header matching (`Txn Dt` → `Transaction Date`) and one-to-one
assignment so two columns cannot claim the same target.

Behind `ERAKSHAK_VALUE_TYPING` so both arms of a measurement run the same build.

Verified: a statement whose headers match **zero** profile aliases (`Posting Stamp`,
`Ledger Folio`, `Money Out`) yields 12/12 events with correct direction. Flag off, the same
file is rejected whole.

### Alias precedence beats raw column order

`Tran_Date`, `pstd_dt` and `value_dt` all alias to `timestamp_start`. Resolution was by raw
column order, so the rightmost won — an empty `value_dt` overwrote a clean `11-12-2019`,
and `pstd_dt`'s `11DEC2019:09:07:02` (a Finacle format `dateutil` rejects whole) took
**95% of bank rows** with it. Now: non-empty beats empty, then the profile's own ordering.

### A date-less value is refused, never dated today

`"Time"` was added as a `timestamp_start` alias for exchange ledgers. `parse_dt("13:45:00")`
returned **today's date** — so a 2019 row would enter the timeline dated now, and because
every such row gets the *same* fabricated date they cluster within minutes and can
**manufacture correlation hits**. Now refused via a two-probe parse, making it a counted
reject.

### Multi-page statements are one table, not forty

Stacked-table splitting was added for portal exports that paste several tables into one
grid. First attempt measured **−420 transactions**: a 40-section "split" was one multi-page
statement repeating its header, and later sections were stranded without the document's
account block, which `_norm_bank` drops rows for. Fixed by merging consecutive identical
headers and giving every section the preamble identity.

### IP sessions are identified by the NAT tuple

De-dup keyed on `(subscriber, public_ip, start)`. TRAI exports repeat the MSISDN on every
row and often leave Public IP blank, so **37 of 75 rows** were dropped as "duplicates" when
they were distinct connections to different destinations. Losing which destinations were
contacted is losing the evidence. Key now carries `private_ip`, `port`, `dest_ip`, `end`.

### `registered_mobile` only bridges when the account matches

On NCRP complaint tables the header subject is often the *complainant* while row accounts
are mule layers. Attaching that phone to every row would falsely merge victim↔mule. The
bridge is only made when the event account equals the header account.

This is the single most important safety decision in the entity model. **Never fabricate an
identity link** — a false account↔phone pair puts an innocent person inside a correlation
hit.

### A non-IST profile may never win on values alone

`crypto_exchange_ledger` is `source_tz: UTC` with 7 fields against `bank_generic`'s 12, and
the coverage ratio let it claim a rupee statement — shifting **every timestamp by 5.5
hours, silently**. In a window-based correlation product that does not merely lose hits, it
manufactures and destroys them. Ranking now uses absolute evidence.

---

## Reject accounting

### `rejected_rows` keeps its meaning; new information gets new fields

Split into `non_evidentiary_rows` (duplicates, blank padding) and `unmapped_rows` (genuine
mapping failures). On `FIR-0006-2025 U`, 168,735 of 302,597 rejects are non-evidentiary —
**56% of the headline was not lost evidence.** Older figures still compare because the
original field was not redefined.

### Files never opened are now recorded

`_walk` only parsed extensions in `FORMAT_BY_EXT` and dropped everything else with **no
trace** — 125 files in one case, 267 in the other. And `ParsedFile.rejects` never reached
`Investigation.rejects`, because the normalizer's return value replaced the list wholesale.

A row that fails to map is at least counted; a file never opened was **unknowable from the
output**. That is the worse failure for a tool whose job is to say what the evidence
contains.

---

## Platform

### No default credential ships

Unset password variables produce a random one per boot, logged once. A `:-analyst` fallback
in compose was added and then **reverted** — it replaced a random credential with a known
one, which is worse than having none.

Credentials are seeded eagerly at boot via a lifespan hook, because lazy seeding logged the
generated password only on first sign-in — and nobody can sign in without first reading it
out of the log.

### Multi-stage image, non-root

Compiler toolchain stays in the builder: 1.98 GB → 1.57 GB, and a forensic image that
parses attacker-supplied archives no longer ships `gcc` or runs as root (uid 10001).

Healthchecks live per-service in compose, not in the Dockerfile — one image serves two
roles, so a single baked probe would mark the dashboard permanently unhealthy.

### The NL answer is composed locally

`/v1/query` returns an `answer` sentence templated in `answer.py` from the validated spec
and the local result set. **Rows are never sent to the LLM to write prose** — that would
breach the data boundary. The generated `spec` is returned as the audit trail.

---

## Process decisions

### Re-measure before fixing

Three requirements went green on 30 Jul with **no new code** — the recorded figure was
stale. This is now the first step for any item on the backlog.

### FR-4's headline was the wrong unit

"658 of 951 unrecognised" counts **tables**, which average 24 rows against thousands in the
claimed ones. By rows: **95.6%** and **97.8%** claimed. The genuine parser gap across both
cases is **3 tables / 92 rows = 0.008%** of 1,114,168 rows. The rest is out of scope (a
CCTV log is 70% of one case's residue), refused on purpose, or reference data with no time
anchor.

A percentage is meaningless until you know what it counts.

### Two agents, one checkout

`git add -A` from session A swept 581 lines of session B's in-progress `value_typer.py` into
a commit about reject accounting. Nothing was lost, but the history misattributes it.
Recorded rather than rewritten — rewriting pushed history over a labelling error is worse
than the error.

Both sessions then independently planned the same dead-letter fix within minutes. See
`../../COORDINATION.md` for the resulting protocol: explicit paths only, the container is a
mutex, and a live claims table.

---

## Claims withdrawn

Kept because the reasoning failure is more instructive than the number.

| Claim | What was wrong |
|---|---|
| "27,713 recoverable rows in unrecognised files" | inflated; then revised *down* to "two thirds is padding" on the evidence of **one** file; the real figure was 25,356 with 1% blank. Generalising from one sample. |
| "`rejected_rows` is inflated by blank padding" | measured 185 blank rows in 378,812 — but that number came from the **broken collection path** B later found. The entries were produced and discarded. True figure was unknown, not small. |
| "FR-18 heat maps not implemented, zero matches" | the grep was case-sensitive. It existed in Streamlit all along. |
| "the amount gate is why layering under-fires" | floor lowered 10,000 → 1,200, eligible rose to 4,710, rules fired **identically**. |
| "the account↔phone bridge is what blocks FR-9" | bridge built, `account+phone` 2 → 30, STRONG **stayed 0**. The IP leg is the constraint. |
| `mule_account` "eligible = 9,996" | eligibility was an entity count wearing a diagnosis; real figure 6. |

The pattern: **the measurements held; the reasoning around them was the weak point.** Four
of the six were caused by trusting a single sample or an instrument that was itself broken.

---

## Traps added 31 Jul

Four things that look like defects and are not, and one that looked like nothing and was the
worst bug found in the project. Each cost real time to establish, so they are written down
rather than left to be rediscovered.

### `common_imei.py` skips 5 of 8 `Common_*_Report` files — leave it alone

Operators ship the whole family into one CDR folder and the filename match claims only
`common_imei`. That reads as five free files. Check the column semantics before touching it:

| report | `Number` column | wide columns | what it means |
|---|---|---|---|
| `Common_IMEI_Report` | IMEI | MSISDN | identity — **claimed** |
| `IPDR_-_Common_IMEI_Report` | IMEI | session stems | identity — **claimed** |
| `Common_A_B_Report` | MSISDN, **and SMS sender IDs** like `VG-ViCARE` | MSISDN | a *comms* edge |
| `Common_First_Cell_ID_*` | **cell ID** | MSISDN | a *location* edge |

Two A-parties sharing a B-party says nothing about who owns what, and an SMS header is not a
subscriber. Merging a **cell tower** into a phone entity would fuse every handset that ever used
that cell into one subject. One of those cell IDs is 15 digits and passes the IMEI length test —
the filename is the only thing keeping it out.

So the narrow match is correct, and it was correct for a reason nobody had written down.
`test_common_imei_refuses.py` now pins each refusal, so widening it breaks a test rather than a
case.

### `amount("Rs.75,00,000")` returned `0.75`

The worst bug found in this project, and it was not Gujarati-specific — Latin `Rs.` did it too.
The character filter kept the dot belonging to `Rs.` and dropped the grouping commas, leaving
`.7500000`, which `float()` reads as a fraction. **A ₹75-lakh transfer recorded as 75 paise,
silently**, feeding `total_in`, the `structuring` band test, `layering`'s minimum-amount floor,
the risk score and the STR alike. No reject entry, no symptom.

It surfaced only because the police affidavits write `રૂ.૭૫,૦૦,૦૦૦/-`. The `/-` variant failed
loudly and returned `None`; the bare `Rs.` form did not. **Loud failures are not the dangerous
ones.**

### `\d` is Unicode-aware, so Gujarati digits passed every digit test uncorrected

`re.sub(r"\D", "", …)` treats `૦-૯` as digits and **keeps** them, so `phone()` returned
`+91૯૮૭૬૫૪૩૨૧૦` — a well-formed-looking E.164 string that can never compare equal to its ASCII
twin. PHONE, ACCOUNT_NO and IMEI are all merge keys, so one person written both ways became two
entities with no reject entry and no symptom. **A missed identity link must not be quieter than a
fabricated one.**

Fixed with one shared `core.text.ascii_digits` over nine Indian scripts. `value_typer` had its
**own** copy of `_digits`, which is how half the fix got missed on the first pass — a test now
asserts both layers resolve to the same object.

Measured yield: **+1 transaction**. Stated plainly because an audit does not justify itself by its
size. The identifier columns in the real evidence are ASCII; the Gujarati numerals are in prose
and amounts. The value is latent — the next case folder is a different police station.

### 47 exhibits were never delivered

Every `.docx` the readers cannot open — 47 across both cases — is **exactly 162 bytes**, each
holding a length-prefixed source host name: `HP` (15), `ACER` (13), `pc` (8), `Admin` (6),
`CYBER` (3), `admin` (2). Six different machines. They are shortcut / cloud-placeholder stubs:
the documents' bytes were never copied into the evidence set, and the originals as delivered fail
identically, so our staging did not cause it.

They now reach the reject report saying so, with a `content_never_delivered` flag, because
**"unreadable" invites someone to try a better parser while "never delivered" is a request to the
case officer.** A genuinely corrupt file is still reported as corrupt — claiming the wrong one
would send the officer hunting for a file we already hold.

### Do not put case identifiers in these docs

`DECISIONS.md` carried live MSISDNs, IMEIs and IMSIs, and got committed and pushed to the remote.
The identifiers have been redacted and the argument survives intact — what mattered was that all
six appear in **zero files outside `ipdr/`**, never the values themselves. Reproduce against the
live folder with `grep -rl`, and keep the result out of the file.

The same rule that keeps `datasets/` out of git applies to anything written *about* the evidence.
MEMO to reviewers: identifiers here are redacted on purpose; do not "restore" them for clarity.
