# ERakshak — next work order (round 3)

Paste into Cursor. Every number below was independently re-measured on this machine, not
copied from your report.

---

## 0. Your last round — verified

| Claim | Verified? |
|---|---|
| ruff pass | ✅ |
| pytest 140 passed | ✅ 140 |
| tsc / npm build / vitest | ✅ all pass |
| STRONG unchanged at 0 | ✅ |
| `correlation_hits_medium` = 2 | ✅ |
| every other metric unchanged | ✅ events 224,167 · txns 21,052 · calls 203,046 · ip 69 · entities 4,131 · transfers 12,527 |
| locked: 7 archives / 31 members | ✅ exactly 31 encrypted members in 7 archives |

**Also now done, which you had left in the queue:** the Gemini six-question set runs
**6/6**, 1.2–5.1 s each. Your timeout fix works. C3 is closed.

**MEDIUM = 2 independently re-derived.** I did not read the correlator's own tally — I
walked all 224,167 events, grouped call and transaction timestamps per entity, and ran my
own bisect:

```
entities with CALL + TXN anywhere        : 10
entities with CALL + TXN within W=10min  :  2      (E02386, E01673)
```

Exactly your number, and your explanation for why it is 2 rather than ~10 is correct. Also
confirmed: `detection/service.py` contains no reference to the MEDIUM tier, so risk scoring
really is STRONG-only.

Good call on the tiering. `correlation_hits` still means STRONG, `correlation_hits_medium`
is separate, and risk scoring stayed STRONG-only. That is the right shape.

---

## 1. STRONG is impossible on this evidence — now proven, not inferred

You said the IPDR phones never appear in the CDR. I verified it at the **source-file**
level rather than the entity level, which is stronger evidence than either of us had:

```
IPDR MSISDNs : 7500107305, 8535088505
IPDR IMEIs   : 355330170920575, 358419296846579
IPDR IMSIs   : 405870182224029, 405870182365083

each of the six, searched across cdr/ :  0 files
each of the six, searched across the ENTIRE case folder outside ipdr/ :  0 files
```

Those identifiers exist **nowhere in the case except the IPDR files themselves**. So
STRONG cannot fire, and no amount of parser work will change that. Record this in
`docs/GAP_ANALYSIS_REAL_DATA.md` as a **measured, closed-out conclusion** with those
counts — it is a legitimate finding, not a failure.

### One correction to your framing

You wrote that locked CDRs "include numbers near the IPDR set (e.g. 8535088005 in a locked
zip vs IPDR 8535088505)". Those are **different numbers** — `…88005` vs `…88505`. Near-miss
digits are not a lead, and presenting them as one invites someone to chase it.

More importantly: **all 7 locked archives are CDR or IMEI — none is IPDR.**

```
CDR__1367__SP10024760.zip          CDR__4169__SP11102422.zip
CDR__6608__MSISDN_…tar.gz.zip      CDR__6857__SP9252797.zip
imei__6607__airtel__SP9086079.zip  imei__SP9045917.zip
upload__0065_soft_file__…zip
```

A password therefore adds **CDR coverage, not IP sessions**. It can only produce STRONG if
an unlocked CDR happens to contain `7500107305` or `8535088505` — which is the one
hypothesis still untestable without the password. State it that precisely; do not imply
the password is likely to unblock FR-9.

**Action:** ask the case officer for the archive password, and write down that everything
else about STRONG is blocked on evidence, not code.

---

## 2. Where the actual headroom is

STRONG is capped by evidence. **MEDIUM is capped by us**, and that is where to work.

```
entities with CALL + TXN anywhere : 10
entities with CALL + TXN within W : 2      <-- today's MEDIUM
entities with ACCOUNT_NO + PHONE  : 0      <-- the real ceiling
ACCOUNT_NO appears on 388 entities, PHONE on 8,141
```

Only 2 coincide inside W because bank and telecom identities are still **separate
entities**. The 10 exist purely through UPI-VPA mining in narrations. Merge the identities
and both numbers rise sharply.

### P1 — the account↔phone bridge (highest value now)

1. **`datasets/entity_map.template.csv` is still untried.** Fill it from KYC (account ↔
   registered mobile) and re-measure. This is the fastest lever in the whole system.
2. **`header_identity.registered_mobile`** is already supported by the bank profile.
   Measure how many real statements actually carry a mobile in the header block and how
   many are being dropped. Report the count either way.
3. **UPI-VPA mining already works** — it produced all 10. Measure its yield and widen the
   pattern set if the data supports it.

Expected: MEDIUM well above 2. State your expected number *before* you run it.

### P2 — 58,416 unrecognised rows, and SOA PDFs are in there

This is now the largest reject bucket, bigger than BANK's 4,665. You noted it is "mostly
SOA PDFs / CCTV txt / statements". **SOA PDFs are bank statements** — those are
transactions being thrown away, and every recovered one feeds P1.

Use the method that found the last three bugs: take the worst file from
`/v1/data-quality`, trace **one** row through
`parse_file → map_record → parse_dt → _norm_bank`, read the reject reason. Do not guess.

### P3 — `fir-0006-2025-u` has still never completed an end-to-end run

1,006 files, 676 MB, the second real case. Nobody has run it. Do it, and report the same
metric table. Do not quote any figure for it until you have.

### P4 — nobody has used the UI

`/ask` and `/quality` compile and serve 200, but no one has typed a question, expanded a
QuerySpec panel, or read the reject table in a browser. Drive it and report what breaks.

---

## 3. Verify like this

**State the expected number before you look. Then measure. Then diff everything.**

```bash
docker compose up -d --build
docker compose exec -T api ruff check backend tools scripts
docker compose exec -T api sh -c "pytest backend/tests -p no:warnings 2>&1 | tail -2"
cd frontend && npx tsc --noEmit && npm run build && npx vitest run
```

```
POST /v1/analyze  {"dataset":"fir-65-2024","window_minutes":10}
GET  /v1/data-quality/fir-65-2024?window=10
```

Diff **every** metric, not just the one you targeted. Explain anything that moved
unexpectedly, including numbers that went down. If a number does not move, say so.

**Do not trust a count a feature reports about itself.** I re-derived MEDIUM by walking all
224k events and doing my own bisect on call/transaction timestamps per entity, rather than
reading the correlator's own tally. Do the same for anything you add.

### Traps already paid for here

- **A zero is ambiguous** — it looks identical whether a feature works and found nothing or
  is broken. Re-run against data known to contain a hit. This is how the 10 CALL+TXN
  entities surfaced from an apparent "0 correlations".
- **`/app` is `COPY`ed into the image, not bind-mounted.** Host edits do not reach a
  running container. Always `docker compose up -d --build`.
- **Never run a second `_analyze` in the API container** — a duplicate ~3.5 GB copy
  OOM-kills it. Go through the HTTP API.
- **Do not rebuild while a long analyse runs** — it kills the run. Cost me 13 minutes.
- **A cold `fir-65-2024` analyse is ~13 min** and pins a GIL-holding worker, so the API is
  unresponsive throughout. Not a hang.
- **Run the whole suite, never one file** — users seed into a module-level cache, so tests
  can pass alone and 401 together.

---

## 4. Rules that do not bend

1. **The LLM never sees case data** — question plus schema vocabulary only.
   `_assert_no_case_data` enforces it; `answer.py` composes the sentence locally. Both
   verified clean of network calls this round. Keep it that way.
2. **Nothing is dropped silently.** Every rejected row counted and surfaced with a reason.
3. **Real evidence never reaches git.** `git status --porcelain` must show no FIR files, no
   `.env`, no `*.db`. Note: I had to add `artifacts/` to `.gitignore` this round — a scratch
   script there had a real NCRP complaint reference hardcoded and was committable.
4. **Never inflate a headline metric to pass a gate.** You handled this correctly with
   `correlation_hits_medium`; keep that discipline.
5. **Update `docs/GAP_ANALYSIS_REAL_DATA.md`** whenever a gap opens, closes or moves, with
   before/after numbers.

---

## 5. Report back with

- ruff / pytest / tsc / build / vitest, with counts
- before → after for every pipeline metric
- MEDIUM count after the bridge work, and confirmation STRONG is still 0 for the reason in
  §1 rather than a regression
- `fir-0006-2025-u` full metric table
- for anything unfixed: the measured numbers that say why
