"""Script-level text utilities shared by ingestion and normalization.

Lives in `core` because both layers need it and `ingestion` must not import `normalization` —
that is backwards from the pipeline order, and the same helper was already duplicated once,
which is how half the fix got missed the first time.
"""

from __future__ import annotations

import re

#: Zero codepoint of every decimal-digit block that can appear in Indian case material, plus
#: Arabic-Indic and fullwidth forms seen in exports. Enumerated rather than discovered by
#: scanning Unicode for category Nd, because a forensic tool should state exactly which scripts
#: it accepts and an auditor should be able to read the list.
DIGIT_BLOCK_ZEROS = (
    0x0966,  # Devanagari    ०-९
    0x09E6,  # Bengali       ০-৯
    0x0A66,  # Gurmukhi      ੦-੯
    0x0AE6,  # Gujarati      ૦-૯
    0x0B66,  # Oriya         ୦-୯
    0x0BE6,  # Tamil         ௦-௯
    0x0C66,  # Telugu        ౦-౯
    0x0CE6,  # Kannada       ೦-೯
    0x0D66,  # Malayalam     ൦-൯
    0x0DE6,  # Sinhala       ෦-෯
    0x0660,  # Arabic-Indic  ٠-٩
    0x06F0,  # Extended Arabic-Indic ۰-۹
    0xFF10,  # Fullwidth     ０-９
)

_DIGIT_TRANSLATION = {zero + d: str(d) for zero in DIGIT_BLOCK_ZEROS for d in range(10)}

_NON_DIGIT = re.compile(r"\D")


def ascii_digits(value) -> str:
    r"""Rewrite decimal digits from any supported script as ASCII 0-9.

    `\d` in a `str` pattern is **Unicode-aware**, so `re.sub(r"\D", "", ...)` treats Gujarati
    ૦-૯ as digits and keeps them. Every "is this a digit" test therefore passed while the value
    was never converted, and `phone()` returned `+91૯૮૭૬૫૪૩૨૧૦` — a well-formed-looking E.164
    string that can never compare equal to the same number written in ASCII. PHONE, ACCOUNT_NO
    and IMEI are all merge keys, so the same person arrived as two entities and the link was
    simply absent, with nothing in the reject report to say so. A missed identity link must not
    be quieter than a fabricated one.

    Non-digit characters are untouched, so an account number carrying letters survives intact.

    73% of the files in `FIR-0006-2025 U` have Gujarati in their path, and the narrative police
    documents write amounts, dates and mobile numbers in Gujarati numerals while writing account
    and IMEI numbers in ASCII — often in one sentence. Both forms must normalise to one value.
    """
    if value is None:
        return ""
    s = str(value)
    return s if s.isascii() else s.translate(_DIGIT_TRANSLATION)


def digits_only(value) -> str:
    """Digits of `value` in ASCII, everything else removed.

    Feeds IMEI/IMSI matching and the value-based column typer, whose length, Luhn and
    MCC-prefix tests a non-ASCII digit passes structurally and then fails on comparison.
    """
    return _NON_DIGIT.sub("", ascii_digits(value)) if value is not None else ""
