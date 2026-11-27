"""Postprocess stage (launch/05-RAG-V2-SPEC.md 3.9): sanitise HTML,
optional PII redaction, and follow-up suggestion generation.
"""
import asyncio
import logging
import re

from app.providers.router import ProviderError, get_router

log = logging.getLogger(__name__)

FOLLOWUP_TIMEOUT_SECONDS = 2.0

_ALLOWED_TAGS = {"b", "i", "em", "strong", "a", "code", "pre", "ul", "ol", "li", "br", "p"}
_ALLOWED_ATTRS = {"a": ["href"]}

_PII_PATTERNS = [
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b"), "[PHONE]"),
    (re.compile(r"\b(?:4\d{3}|5[1-5]\d{2}|6011|3[47]\d{2})[-\s]?\d{4,}\b"), "[CARD]"),
]

_FOLLOWUP_SYSTEM = (
    "Given the EVIDENCE and ANSWER below, suggest 2-3 short follow-up questions "
    "the user might want to ask next. Respond with JSON only: "
    '{"follow_ups": ["question 1", "question 2", ...]}.'
)


def sanitize_html(text: str) -> str:
    try:
        import bleach
        return bleach.clean(
            text,
            tags=_ALLOWED_TAGS,
            attributes=_ALLOWED_ATTRS,
            strip=True,
        )
    except ImportError:
        log.warning("bleach not installed, skipping HTML sanitisation")
        return text


def redact_pii(text: str) -> str:
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


async def suggest_follow_ups(answer: str, evidence_summary: str, count: int = 3) -> list[str]:
    if count <= 0:
        return []
    try:
        router = get_router()
        result = await asyncio.wait_for(
            router.complete_json(
                [
                    {"role": "system", "content": _FOLLOWUP_SYSTEM},
                    {"role": "user", "content": f"EVIDENCE:\n{evidence_summary}\n\nANSWER:\n{answer}"},
                ],
                max_tokens=200,
            ),
            timeout=FOLLOWUP_TIMEOUT_SECONDS,
        )
        follow_ups = result.get("follow_ups")
        if not isinstance(follow_ups, list):
            return []
        return [str(f).strip() for f in follow_ups if str(f).strip()][:count]
    except (asyncio.TimeoutError, ProviderError, ValueError, TypeError) as exc:
        log.warning("follow-up suggestions failed (%s)", exc)
        return []


def postprocess(text: str, *, pii_redaction: bool = False) -> str:
    text = sanitize_html(text)
    if pii_redaction:
        text = redact_pii(text)
    return text
