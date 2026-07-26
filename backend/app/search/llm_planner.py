"""Natural language -> validated QuerySpec, via the Google Gemini API (F1, FR-19).

**This is the only module that talks to an external API, and it never sends case data.**

What goes out: the analyst's question, plus a static vocabulary of field/operator names
(`dsl.schema_vocabulary()`). What comes back: a `QuerySpec` object, constrained by Gemini's
structured-output mode against the Pydantic schema. The spec is then executed locally by
`dsl.execute` — no records, names, phone numbers or account numbers ever leave the machine.

That split is the SR-R4 mitigation from `research/10_risk_analysis.md` and the design
`research/07_architecture_planning.md` chose: "LLM emits a validated structured DSL, never
raw SQL". `_assert_no_case_data` enforces it at runtime rather than trusting the caller.

Model: `gemini-2.5-flash` — a free-tier model. Translating one question into a small JSON
object with enum-constrained fields is an easy task, so the larger tiers buy nothing here
and cost quota. Set GEMINI_MODEL to override (`gemini-2.5-flash-lite` is lighter still).

Without an API key this module returns None and the API falls back to the offline
rule-based interpreter, so the system never hard-depends on network access — which matters
for an evidentiary tool that may run air-gapped.
"""

from __future__ import annotations

import json
import os

from ..core.logging_config import audit, get_logger
from .dsl import QuerySpec, schema_vocabulary

log = get_logger(__name__)

#: Free-tier lite model, ample for query planning. Override with GEMINI_MODEL.
#: The "-latest" alias is deliberate: pinning a dated model breaks silently when Google
#: retires it for new keys (gemini-2.5-flash already 404s with "no longer available to
#: new users"), and this planner degrades to the rule engine rather than erroring — so a
#: retirement would look like "the LLM just stopped working" with no signal.
DEFAULT_MODEL = "gemini-flash-lite-latest"

_SYSTEM = """You translate an investigator's question into a structured query object for \
ERakshak, a forensic tool that fuses bank statements, call records (CDR) and internet \
session records (IPDR) onto one timeline.

You are given only the query vocabulary below — never the case data itself. Produce a \
query that answers the question using those fields. Never invent a field or operator name.

Guidance:
- "who did X call most often" -> target=events, filter event_type=CALL and phone/entity, \
group_by=counterparty, aggregate=count.
- "calls between 2am and 5am" -> filter field=hour_of_day, op=between, values=[2,5].
- "which numbers shared an IMEI" -> target=events, group_by=imei.
- "transfers over N" -> target=events, event_type=TRANSACTION, amount gte N.
- "high risk entities" -> target=entities, risk_band eq high.
- Prefer a group_by when the question asks "who/which ... most/top".

Questions a plain filter cannot express — use the right construct:
- Anything relative to another event ("the day before the last transaction", "the week \
after the first call") -> set `relative_window` with an anchor, offset_days (negative = \
before) and span_days. Do NOT try to express this as a date filter; the date is not known \
until the data is read.
- Anything about absence or a group's own history ("numbers that stopped calling after \
August", "accounts with no activity since March", "entities with more than 50 calls") -> \
group_by the subject, then a `having` clause on last_seen / first_seen / count. A plain \
filter would return the busiest rows, which is the opposite of "stopped".
- "called both A and B", "used by both X and Y" -> group_by the subject and set \
`group_must_include` with the field and every required value.
- "mentions X anywhere" / a term you cannot map to one field -> filter on `any_text` \
with `contains`.

Set `explanation` to one plain sentence the analyst will read above the results.

Vocabulary:
{vocab}"""

# Anything that looks like case data must never appear in an outbound prompt. A question
# legitimately contains a phone number ("calls to 9702000558"), so digits alone are fine —
# what must not appear is a bulk record dump.
_MAX_QUESTION_CHARS = 500

#: The SDK itself reads either of these; checked here so `available()` matches its behaviour.
_KEY_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY")


def _assert_no_case_data(question: str) -> None:
    """Guard the boundary: only a short question may leave the machine.

    Cheap and strict on purpose. It is not trying to classify PII — it enforces that the
    payload is a question, not a payload of records, so a future caller cannot quietly
    start passing rows through here.
    """
    if len(question) > _MAX_QUESTION_CHARS:
        raise ValueError(
            f"refusing to send {len(question)} chars to the LLM: questions are capped at "
            f"{_MAX_QUESTION_CHARS}. This guard exists so record data cannot be passed here."
        )
    if question.count("\n") > 5:
        raise ValueError("refusing multi-line payload: expected a single question")
    # A tabular fragment (repeated delimiters) is a record dump, not a question.
    if question.count(",") > 12 or question.count("|") > 6 or question.count("\t") > 2:
        raise ValueError("refusing delimited payload: expected a question, not records")


def available() -> bool:
    return any(os.getenv(v) for v in _KEY_VARS)


def _gemini_schema() -> dict:
    """QuerySpec as a schema Gemini will accept.

    The Pydantic models set `extra: "forbid"` so a malformed spec fails validation
    locally. That emits `additionalProperties`, which Gemini's structured-output endpoint
    rejects outright ("Unknown name 'additional_properties'"), as do `title`/`default`.
    Strip them for the wire; local validation still enforces strictness on the way back.
    """
    def strip(node):
        if isinstance(node, dict):
            return {k: strip(v) for k, v in node.items()
                    if k not in ("additionalProperties", "title", "default")}
        if isinstance(node, list):
            return [strip(v) for v in node]
        return node

    return strip(QuerySpec.model_json_schema())


def plan(question: str, *, model: str | None = None) -> QuerySpec | None:
    """Translate `question` into a QuerySpec, or None if unavailable / not translatable."""
    if not available():
        return None
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        log.info("google-genai SDK not installed; using the rule-based query interpreter")
        return None

    _assert_no_case_data(question)
    vocab = json.dumps(schema_vocabulary(), indent=2)

    try:
        client = genai.Client()          # reads GEMINI_API_KEY / GOOGLE_API_KEY
        response = client.models.generate_content(
            model=model or os.getenv("GEMINI_MODEL") or DEFAULT_MODEL,
            contents=question,
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM.format(vocab=vocab),
                # Constrained decoding: the model cannot return a shape the executor
                # would reject.
                response_mime_type="application/json",
                response_json_schema=_gemini_schema(),
                temperature=0,           # planning is deterministic, not creative
            ),
        )
        # Validate locally rather than trusting the constraint — `extra: forbid` still
        # applies here, so an unexpected field is caught rather than silently ignored.
        spec = QuerySpec.model_validate_json(response.text or "")
    except Exception as e:               # network, auth, quota, schema, validation
        log.warning("LLM query planning failed (%s); falling back to rules", e)
        return None

    # Audit the question and the plan — never the results. This is the evidentiary record
    # of how a natural-language answer was derived.
    audit("nl_plan", question=question, spec=spec.model_dump(mode="json"))
    return spec


__all__ = ["DEFAULT_MODEL", "available", "plan"]
