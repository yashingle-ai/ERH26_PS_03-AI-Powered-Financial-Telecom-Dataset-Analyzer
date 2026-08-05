# Rule-4 finding — live case identifiers are in git, and on the public remote

**Found:** 5 Aug 2026, incidentally, while running the rule-4 grep before a documentation commit.
**Status:** **open — needs a decision from the repository owner.** Nothing has been rewritten.
**Severity:** high. This is the rule `CLAUDE.md` calls out as worse than shipping nothing.

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

The remote is a **public GitHub repository**. The identifiers have therefore been publicly
available for roughly eleven days and must be assumed cloned, cached and indexed. Deleting them
now removes them from the working tree, not from anyone's copy.

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
| **A** | Redact the working tree only — replace real numbers with generated placeholders in tests, source, config and docs; blank the template's example block | Stops *further* publication; history unchanged | Low. Tests referencing the values need updating together, so the suite stays green |
| **B** | A, plus make the repository private | Removes the public exposure going forward | Low, if no public visibility is required |
| **C** | A + B, plus rewrite history (`git filter-repo`) and force-push | Removes the values from the repository's own history | High — invalidates every existing clone, and the two collaborators must re-clone. Forks, caches and GitHub's own archived views may retain them regardless |

**Realistic assessment:** option C does not undo publication. Anything public for eleven days
should be treated as disclosed. Its value is stopping the repository from continuing to serve the
data, not restoring confidentiality.

**Worth raising with whoever owns the case material**, independently of what is done to the
repository. These are subjects of an active FIR, and the question of whether their identifiers were
disclosed is not an engineering question.

## 6. What was done on 5 Aug

- Fixed the rule-4 grep in `CLAUDE.md` — `git grep`, every tracked text type, no broken glob.
- Wrote this file.
- **Made no redactions and rewrote no history.** Options A–C above are the owner's call.

If A is chosen, note that the five MSISDNs are load-bearing in `backend/tests/test_bridge.py` and
`backend/tests/test_common_imei_refuses.py` — the latter pins the refusal behaviour that stops a
cell tower being merged into a phone entity. Substitute placeholders in the fixtures and the
assertions in the same change, then run the full suite; do not delete the tests.
