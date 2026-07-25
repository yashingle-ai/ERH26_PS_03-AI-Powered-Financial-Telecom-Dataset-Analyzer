"""Natural language -> validated QuerySpec, via Claude (F1, FR-19).

**This is the only module that talks to an external API, and it never sends case data.**

What goes out: the analyst's question, plus a static vocabulary of field/operator names
(`dsl.schema_vocabulary()`). What comes back: a `QuerySpec` object, validated by the SDK
against the Pydantic schema. The spec is then executed locally by `dsl.execute` — no
records, names, phone numbers or account numbers ever leave the machine.

That split is the SR-R4 mitigation from `research/10_risk_analysis.md` and the design
`research/07_architecture_planning.md` chose: "LLM emits a validated structured DSL, never
raw SQL". `_assert_no_case_data` enforces it at runtime rather than trusting the caller.

Absent ANTHROPIC_API_KEY this module returns None and the API falls back to the offline
rule-based interpreter, so the system never hard-depends on network access — which matters
for an evidentiary tool that may run air-gapped.
"""

from __future__ import annotations

import json
import os

from ..core.logging_config import audit, get_logger
from .dsl import QuerySpec, schema_vocabulary

log = get_logger(__name__)

DEFAULT_MODEL = "claude-opus-5"

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
- Set `explanation` to one plain sentence the analyst will read above the results.

Vocabulary:
{vocab}"""

# Anything that looks like case data must never appear in an outbound prompt. A question
# legitimately contains a phone number ("calls to 9702000558"), so digits alone are fine —
# what must not appear is a bulk record dump.
_MAX_QUESTION_CHARS = 500


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
    return bool(os.getenv("ANTHROPIC_API_KEY"))


def plan(question: str, *, model: str | None = None) -> QuerySpec | None:
    """Translate `question` into a QuerySpec, or None if unavailable / not translatable."""
    if not available():
        return None
    try:
        import anthropic
    except ImportError:
        log.info("anthropic SDK not installed; using the rule-based query interpreter")
        return None

    _assert_no_case_data(question)
    vocab = json.dumps(schema_vocabulary(), indent=2)

    try:
        client = anthropic.Anthropic()
        response = client.messages.parse(
            model=model or os.getenv("ANTHROPIC_MODEL") or DEFAULT_MODEL,
            max_tokens=2000,
            thinking={"type": "adaptive"},
            # The system block is byte-stable across every request, so it caches; the
            # question is the only varying part and sits after it.
            system=[{
                "type": "text",
                "text": _SYSTEM.format(vocab=vocab),
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": question}],
            output_format=QuerySpec,
        )
    except Exception as e:                       # network, auth, validation, refusal
        log.warning("LLM query planning failed (%s); falling back to rules", e)
        return None

    if response.stop_reason == "refusal":
        log.warning("LLM declined to plan the query; falling back to rules")
        return None

    spec = response.parsed_output
    # Audit the question and the plan — never the results. This is the evidentiary record
    # of how a natural-language answer was derived.
    audit("nl_plan", question=question, spec=spec.model_dump(mode="json") if spec else None)
    return spec


__all__ = ["plan", "available", "DEFAULT_MODEL"]
