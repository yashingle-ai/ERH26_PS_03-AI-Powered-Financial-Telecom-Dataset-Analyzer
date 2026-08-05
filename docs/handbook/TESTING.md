# Testing — conventions, and what a good test looks like here

**425 tests across 32 files.** `PYTHONPATH=. python -m pytest backend/tests -p no:warnings`.

`conftest.py` puts the repo root on `sys.path` and offers a session-scoped `smoke_dataset` fixture
that generates a small synthetic case from `tools/synthetic_data_generator`. `pyproject.toml` sets
`addopts = "-q"`, which is why there is no summary line — count with
`--collect-only -q | awk -F': ' '/: [0-9]+$/{s+=$2} END{print s}'`.

---

## 1. Two non-negotiables

**Fixtures are synthetic. Always.** Case material must not enter the repository, and that includes
test data. Where a test needs the *shape* of real evidence, reconstruct the shape and invent the
values:

```python
# the real five-column Gujarati bank-reply header, transliterated in a comment so a
# reviewer who does not read Gujarati can audit the match
HEAD = ["અ.નં.", "બેંક એકાઉન્ટ નંબર", "એકાઉન્ટ ધારકનું નામ સરનામુ",
        "રજીસ્ટર મોબાઇલ નંબર", "રજીસ્ટર ઇ-મેઇલ આઇડી"]
```

`test_indic_numerals.py` builds every value by transliterating invented numbers into nine scripts —
no exhibit is copied.

**Write the test that would have caught the bug**, not one that passes. Every test file here opens
with the defect it exists to prevent, because a test whose purpose is unclear gets deleted in six
months by someone who cannot tell it from redundancy.

---

## 2. Test the refusal, not just the happy path

For anything that creates identity or drops data, the refusals carry more weight. `bank_reply_links`
has 4 acceptance tests and **8 refusal** tests:

| refuses | because |
|---|---|
| an officer/handler column anywhere | the `master - Copy.xlsx` shape — linking it would have merged 32 mule accounts into ~98 police entities |
| no holder column | a seized-property schedule lists an account and a handset without claiming either belongs to the other |
| an English-headed table | that is the profiles' business; two readers claiming one table is how a column gets interpreted twice |
| a shared contact number | one mobile against many accounts is a branch contact, not a holder |
| fan-out measured **per case**, not per table | one shared number spread thinly over six copies of a reply passes every table individually |

`test_common_imei_refuses.py` is the same idea for a trap: it enumerates the four `Common_*_Report`
shapes so that **widening the filename match breaks a test rather than a case**.

---

## 3. Pin the invariant, not the current output

A test asserting today's number breaks on every legitimate improvement. Assert the property.

```python
# not: assert forwarded == 0.75
# but: whatever window the detail names, a forward just past it must not have produced the flag
for hold in (30, 60, 120, 240):
    assert f"within {hold}min" in flags[0]["detail"]
    assert rulemod.rapid_in_out(_in_then_out(hold + 1), _cfg(hold)) == []
```

Close the whole class where you can. This one fails if **any** declared threshold is left unread:

```python
def test_every_declared_threshold_is_read_by_the_rule_that_declares_it():
    raw = yaml.safe_load(open(config.CONFIG_DIR / "scoring_rules.yaml", encoding="utf-8").read())
    src = open(rulemod.__file__, encoding="utf-8").read()
    unread = [f"{rule}.{key}" for rule, params in raw["rules"].items() for key in params
              if key not in ("enabled", "weight")
              and f'"{key}"' not in src and f"'{key}'" not in src]
    assert unread == []
```

Three thresholds were declared in config and read by nothing. That test means a fourth cannot appear.

---

## 4. Assert the wiring, not just the module

Two features here were **built, tested, and unreachable**: the report generator had no HTTP route, and
`rules.eligibility_report` was fully unit-tested with nothing calling it. So:

```python
def test_the_pipeline_actually_calls_the_reader():
    import inspect
    from backend.app import pipeline
    src = inspect.getsource(pipeline.run_base)
    assert "er_bank_reply.enabled()" in src
    assert "er_bank_reply.load_bank_reply_links(input_dir)" in src
```

Crude, and it catches the exact failure that unit tests cannot.

---

## 5. When a test fails, suspect the test

Four of the last several failures were fixture bugs, not code bugs, and each taught something:

| failure | cause |
|---|---|
| `1.0 → 0.998` ML score moved | the fixture routed extra edges *through* the observed entities, changing their own `fan_out` — a legitimate reason to move. **Your own evidence may move your score; other people's may not** |
| `structuring` stopped firing | the fixture had `None` timestamps, which no production credit ever has; the rule now honours `window_hours` |
| `KeyError: max_hold_minutes` | my own cfg omitted a key the real config has. Rules now `.get` with a documented default |
| 2 events expected, 1 returned | the two "good" rows were byte-identical and dedupe removed one |

Read the assertion before changing the code. **Do not weaken an assertion to make it pass** — if the
invariant is wrong, say so and change it deliberately with the reason in the docstring.

---

## 6. Files worth reading first

| file | what it teaches |
|---|---|
| `test_bank_reply_links.py` | how to test something that creates identities |
| `test_common_imei_refuses.py` | how to pin a trap so it cannot be "fixed" |
| `test_rule_windows.py` | property tests + the class-closing YAML test |
| `test_ml_fit_population.py` | an invariant about *who else is in the population* |
| `test_indic_numerals.py` | parametrising across nine scripts with synthetic data |
| `test_unrecognised_reasons.py` | classifier tests, and reject arithmetic that must still sum |
| `test_str_section.py` | truncation-is-a-bug tests for the report |
| `test_store_column_migration.py` | a column added to a model must reach a DB that already exists |
| `test_correctness_fixes.py` | the A1–A5 correctness set — Dr/Cr, timezone, dedupe, crypto assets |

---

## 7. Before you say it works

1. `pytest` and `ruff` clean; `tsc` clean if you touched the frontend.
2. A test that would have caught **this** bug.
3. Measured on a real case — see `MEASUREMENT.md`. Quote the figure **and the dataset path**.
4. If nothing moved, say so.
5. A reject entry for any new skip path (rule 2).
6. Mark it 🟢 in `GAPS.md` so the next agent does not rebuild it.

The frontend has `vitest` configured but very few tests, and no human has ever driven `/ask` or
`/quality` in a browser. `GAPS.md` §4 ranks that as the cheapest remaining source of real defects.
