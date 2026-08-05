# Rule-4 finding — live case identifiers are committed to git

**Found:** 5 Aug 2026, incidentally, while running the rule-4 grep before a documentation commit.
**Status:** **open — needs a decision from the repository owner.** Nothing has been redacted or
rewritten.
**Severity:** **moderate.** The repository is private (§3), so this is not a public disclosure —
but it is still a breach of the rule `CLAUDE.md` calls out as worse than shipping nothing, and the
identifiers travel with any future fork, transfer or visibility change. An earlier revision of this
file rated it *high* on an unverified assumption that the repo was public; see the correction in §3.

**No identifiers are reproduced in this file.** It names files and counts only. Use the grep in
§4 to see the values.

---

## 1. What was found

`datasets/entity_map.template.csv` is tracked by git and carries **five Indian mobile numbers that
the file itself describes as coming from the two real FIR case folders**. Its own comment block says:

> *"THE FIVE NUMBERS BELOW ARE THE ENTIRE ASK — each already has both call and IP activity in the
> case material, so supplying the account it belongs to is enough to make STRONG testable."*

Two are attributed to `FIR 65-2024` and three to `FIR-0006-2025 U`. They are grouped under those
headings in the file. They are not examples; they are the actual subjects of an active
investigation, selected precisely because they appear in the CDR and IPDR.

Three of the five also appear as **uncommented data rows** at the end of the same file, paired with
account numbers and a wallet address.

## 2. Spread

Those same five numbers appear across at least **16 other tracked files**, in four categories:

| Category | Files |
|---|---|
| Test fixtures | `backend/tests/` — `test_bridge.py`, `test_common_imei_refuses.py`, `test_str_section.py`, `test_more_fixes.py` |
| Application source | `backend/app/dashboard/app.py`, `backend/app/normalization/service.py`, `backend/app/search/nl_query.py` |
| Configuration | `config/profiles/cdr/lea.yaml` |
| Documentation | `docs/COMPONENT_STATUS.md`, `docs/PS_COMPLIANCE_AND_FIX_PLAN.md`, `GETTING_STARTED.md`, and four files now in `docs/archive/` |

A wider sweep for the identifier shapes also flags IMEI-length and account-length values in
`backend/app/ingestion/`, `backend/app/search/` and several more test files. Those have **not** been
individually verified as real; the five MSISDNs have, because the template states their provenance
outright.

Not in scope, and not a problem: the ~2,600 hits under `datasets/raw/demo/` and
`datasets/raw/smoke/`. Those are synthetic fixtures produced by the generator and are tracked on
purpose.

## 3. Reach

`git log` puts the template in the repository since **25 Jul** (`a3f1351`), amended **30 Jul**
(`a7709fe`). Both commits are contained in `origin/main`.

**The repository is private** — confirmed by the owner on 5 Aug.

> **Correction, same day.** The first revision of this file stated the remote was a *public*
> GitHub repository and assessed the identifiers as publicly disclosed for eleven days. **That was
> inferred, never verified, and it was wrong.** It is recorded rather than quietly edited out,
> because overstating a finding costs credibility on the next one — the same reason
> `handbook/MEASUREMENT.md` keeps its withdrawn figures.

What this changes, and what it does not:

- **Exposure is bounded by repository access**, not by the internet. Whoever can read the repo can
  read the identifiers: the three collaborators, plus anyone the repo or an organisation grants
  access to, plus any clone already taken.
- **It is still a rule-4 breach.** The rule is "real evidence never reaches git", not "never
  reaches a public git". `datasets/` is deny-by-default in `.gitignore` *and* `.dockerignore`
  precisely so that access control is never the only thing standing between case material and
  disclosure.
- **A private repo can become public**, by a settings change, a transfer, or a fork into an
  account with different defaults. The identifiers would go with it, including through history.
- **Remediation is now cheaper and more likely to work.** A history rewrite on a private repo with
  three known collaborators can genuinely remove the values, because every clone is accountable.
  That was not true under the public assumption.

## 4. Why the existing safety check missed it

`CLAUDE.md` rule 4 documented this command:

```bash
grep -nE "(^|[^0-9])([6-9][0-9]{9}|[0-9]{15,16})([^0-9]|$)" docs/**/*.md CLAUDE.md
```

**`docs/**/*.md` does not mean what it looks like.** Without `shopt -s globstar`, bash expands `**`
exactly like `*` — so the pattern is `docs/*/*.md`. It matches `docs/handbook/*.md` and
`docs/decisions/*.md`, and **skips `docs/*.md` entirely.** Verified on this machine: the expansion
returns 0 matches for `docs/COMPONENT_STATUS.md`.

That single character-class quirk explains the whole picture. `docs/handbook/DECISIONS.md` sat one
level deep, was caught, and was untracked in `abf14dd` — *"Untrack the working notes: DECISIONS.md
carried live case identifiers"*. `docs/COMPONENT_STATUS.md` and `docs/PS_COMPLIANCE_AND_FIX_PLAN.md`
sat at the top level, were never scanned by that sweep, and still carry the numbers today. The
sweep was run, it reported clean, and it was structurally incapable of seeing most of the problem.

It also only ever looked at `.md`. Nothing scanned `.py`, `.yaml` or `.csv`, which is where most of
the spread turned out to be.

**The check is now fixed in `CLAUDE.md`** to use `git grep` across every tracked text type. That
change is safe to make immediately and has been made. Everything else below is not mine to decide.

## 5. Options — for the repository owner

Ordered by cost. These are **not** actions to take without the owner's decision: option C rewrites
published history on a repository other people have cloned.

| | Action | Effect | Cost |
|---|---|---|---|
| **A** | Redact the working tree only — replace real numbers with generated placeholders in tests, source, config and docs; blank the template's example block | Stops the values spreading further; history unchanged | Low. Tests referencing the values must be updated in the same change so the suite stays green |
| **B** | A, plus rewrite history (`git filter-repo`) and force-push | Removes the values from the repository entirely, including history | Moderate — invalidates every existing clone; all three collaborators must re-clone or reset |
| **C** | Leave it, and keep the repository private | No work | The breach persists and travels with any future fork, transfer or visibility change |

**Realistic assessment, revised now the repo is known to be private.** Option B is worth doing and
is likely to actually succeed: with a private repo and three known collaborators, there is no
population of anonymous clones to worry about, so removing the values from history removes them in
practice rather than symbolically. Do **A** regardless — it is cheap, it is the part that stops the
values being copied into the next test fixture, and it is a prerequisite for B.

The ordering that matters: **A first**, then B once the working tree is clean, so the rewrite has a
correct end state to land on.

**Still worth a word with whoever owns the case material**, independently of what is done to the
repository — though the private-repo finding makes this far less urgent than the first revision of
this file implied. These are subjects of an active FIR; who has had read access to the repository
since 25 Jul is the question, and it is not an engineering one.

## 6. What was done on 5 Aug

- Fixed the rule-4 grep in `CLAUDE.md` — `git grep`, every tracked text type, no broken glob.
- Wrote this file.
- **Made no redactions and rewrote no history.** Options A–C above are the owner's call.

If A is chosen, note that the five MSISDNs are load-bearing in `backend/tests/test_bridge.py` and
`backend/tests/test_common_imei_refuses.py` — the latter pins the refusal behaviour that stops a
cell tower being merged into a phone entity. Substitute placeholders in the fixtures and the
assertions in the same change, then run the full suite; do not delete the tests.
