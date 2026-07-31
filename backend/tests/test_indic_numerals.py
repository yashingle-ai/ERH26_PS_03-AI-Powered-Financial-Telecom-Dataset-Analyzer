"""Digits written in an Indian script must normalise to the same value as their ASCII twin.

`\\d` in a `str` pattern is Unicode-aware, so `re.sub(r"\\D", "", ...)` treats Gujarati ૦-૯ as
digits and keeps them. Every "is this a digit" test passed while the value was never converted:
`phone()` returned `+91૯૮૭૬૫૪૩૨૧૦`, a well-formed-looking E.164 string that can never compare
equal to the same number in ASCII. PHONE, ACCOUNT_NO and IMEI are all merge keys, so the same
person arrived as two entities and the link was simply absent — with nothing in the reject report
to say so. A missed identity link must not be quieter than a fabricated one.

Found while auditing Gujarati handling: 73% of the files in `FIR-0006-2025 U` carry Gujarati in
their path, and the narrative police affidavits write amounts, dates and mobile numbers in
Gujarati numerals while writing account and IMEI numbers in ASCII, often in one sentence.

Every value below is **synthetic**. Case material does not belong in the repository, so these are
constructed by transliterating invented numbers rather than copied from an exhibit.
"""

from __future__ import annotations

import pytest

from backend.app.core import text as coretext
from backend.app.ingestion import value_typer as vt
from backend.app.normalization import normalizers as nz

#: 0-9 in each script this must support, keyed by name so a failure says which one broke.
SCRIPTS = {
    "gujarati": "૦૧૨૩૪૫૬૭૮૯",
    "devanagari": "०१२३४५६७८९",
    "bengali": "০১২৩৪৫৬৭৮৯",
    "gurmukhi": "੦੧੨੩੪੫੬੭੮੯",
    "tamil": "௦௧௨௩௪௫௬௭௮௯",
    "telugu": "౦౧౨౩౪౫౬౭౮౯",
    "kannada": "೦೧೨೩೪೫೬೭೮೯",
    "malayalam": "൦൧൨൩൪൫൬൭൮൯",
    "oriya": "୦୧୨୩୪୫୬୭୮୯",
}
GUJ = SCRIPTS["gujarati"]


def tr(text: str, script: str) -> str:
    """ASCII digits in `text` rewritten in `script`. Everything else untouched."""
    return text.translate(str.maketrans("0123456789", SCRIPTS[script]))


# ── merge keys must collapse to one value ───────────────────────────────────────────

@pytest.mark.parametrize("script", sorted(SCRIPTS))
def test_a_phone_normalises_identically_in_every_supported_script(script):
    """The defect that matters most: PHONE is a merge key, so two spellings meant two entities."""
    assert nz.phone(tr("9876543210", script)) == nz.phone("9876543210") == "+919876543210"


@pytest.mark.parametrize("script", sorted(SCRIPTS))
def test_an_account_number_normalises_identically_in_every_supported_script(script):
    assert nz.account_no(tr("04310112135", script)) == "04310112135"


@pytest.mark.parametrize("script", sorted(SCRIPTS))
def test_an_imei_normalises_identically_in_every_supported_script(script):
    assert nz._digits(tr("353544569962756", script)) == "353544569962756"


def test_a_phone_survives_a_gujarati_label_and_separators():
    """Affidavits write the number inline, after a label, with spaces inside it."""
    labelled = "મો.નં." + tr("98765 43210", "gujarati")
    assert nz.phone(labelled) == "+919876543210"


def test_letters_in_an_account_number_are_not_touched():
    """Only digits are rewritten; an alphanumeric account or IFSC must survive intact."""
    assert nz.account_no("AB" + tr("1234", "gujarati") + "CD") == "AB1234CD"


def test_ascii_input_is_returned_unchanged():
    """The fast path. An ASCII string must not be rebuilt character by character."""
    assert nz.ascii_digits("9876543210") == "9876543210"
    assert nz.ascii_digits(None) == ""


@pytest.mark.parametrize("script", sorted(SCRIPTS))
def test_a_date_parses_identically_in_every_supported_script(script):
    assert nz.parse_dt(tr("27/11/2024", script)) == nz.parse_dt("27/11/2024")


# ── the amount corruption ───────────────────────────────────────────────────────────

def test_a_rupee_prefixed_lakh_amount_is_not_read_as_a_fraction():
    """`Rs.75,00,000` returned **0.75** — the dot belonging to `Rs.` survived the character
    filter while the grouping commas did not, leaving `.7500000`. A 75-lakh transfer recorded
    as 75 paise, silently, feeding totals, the structuring band test, layering's minimum-amount
    floor, the risk score and the STR alike."""
    assert nz.amount("Rs.75,00,000") == 7_500_000.0
    assert nz.amount("INR.1,15,50,000") == 11_550_000.0


def test_the_same_form_in_gujarati_gives_the_same_amount():
    guj = "રૂ." + tr("75,00,000", "gujarati") + "/-"
    assert nz.amount(guj) == nz.amount("Rs.75,00,000/-") == 7_500_000.0


def test_the_rupees_only_terminator_is_accepted():
    """`/-` left a trailing hyphen that float() rejected. That at least failed loudly, unlike
    the bare `Rs.` form — but a readable amount should not be refused either."""
    assert nz.amount("75,00,000/-") == 7_500_000.0
    assert nz.amount("40,50,000 /-") == 4_050_000.0


@pytest.mark.parametrize("script", sorted(SCRIPTS))
def test_a_plain_grouped_amount_normalises_in_every_script(script):
    assert nz.amount(tr("21,80,127.46", script)) == 21_80_127.46


def test_genuine_decimals_and_negatives_still_parse():
    assert nz.amount("1,234.56") == 1234.56
    assert nz.amount("0.75") == 0.75
    assert nz.amount("-500") == -500.0
    assert nz.amount("₹75,00,000") == 7_500_000.0
    assert nz.amount("Rs 40,50,000") == 4_050_000.0


def test_a_bare_leading_separator_is_refused_not_guessed():
    """The signature of the corruption above. Amounts here are written `0.75`, never `.75`, so
    a leading separator means the form is unrecognised and the magnitude unknown. Refusing
    produces a visible reject; guessing produced a number indistinguishable from a real one."""
    assert nz.amount(".75") is None
    assert nz.amount(".7500000") is None


def test_empty_and_junk_still_return_none():
    for v in (None, "", "-", ".", "abc", "રૂ."):
        assert nz.amount(v) is None


# ── the block list is a documented contract, not a lucky scan ───────────────────────

def test_every_declared_digit_block_maps_all_ten_digits():
    """Enumerated rather than discovered by scanning Unicode for category Nd, so an auditor can
    read which scripts are accepted. That only holds if the list is complete per block."""
    for zero in coretext.DIGIT_BLOCK_ZEROS:
        for d in range(10):
            assert coretext.ascii_digits(chr(zero + d)) == str(d), f"U+{zero + d:04X}"


# ── the value-based column typer shares the SAME helper, not a second copy ──────────

@pytest.mark.parametrize("script", sorted(SCRIPTS))
def test_the_column_typer_recognises_a_phone_column_in_any_script(script):
    r"""`value_typer` had its own `re.sub(r"\D", "", value)`. Because `\d` is Unicode-aware it
    kept Gujarati ૦-૯, so `_is_phone` rejected a good number (`d[0] in "6789"` cannot match ૯)
    and a headerless Gujarati phone column went unmapped."""
    col = ["9876543210", "9812345678", "9723456789", "9898989898", "9765432109", "9611223344"]
    assert all(vt._is_phone(tr(v, script)) for v in col)


@pytest.mark.parametrize("script", sorted(SCRIPTS))
def test_the_column_typer_checksums_an_imei_on_ascii_digits(script):
    """`_is_imei` and `_is_amount` *accepted* non-ASCII columns already, but only because their
    tests are length-based — right answer for the wrong reason. `_luhn_ok` then ran
    `ord(ch) - 48` across non-ASCII codepoints and computed a checksum from nonsense."""
    imei = "353544569962756"
    assert vt._luhn_ok(vt._digits(tr(imei, script))) == vt._luhn_ok(imei)
    assert vt._is_imei(tr(imei, script))


def test_there_is_only_one_digit_helper():
    """Both layers must resolve to the shared function, or the next fix lands in one of them."""
    assert vt._digits is coretext.digits_only
    assert nz._digits is coretext.digits_only
