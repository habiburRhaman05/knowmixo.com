"""Intent stage (launch/05-RAG-V2-SPEC.md 3.2): classify
intent/severity/language with a cheap LLM call in JSON mode, falling
through to a keyword rules engine when the provider is slow or
unavailable. The emergency fast-path fires `event_outbox('escalation.requested', ...)`
immediately, in parallel with the rest of the pipeline -- the full
severity classifier + rule engine (D5.3) consumes that same event
topic; this stage only needs to catch genuine life-safety language fast
enough to trigger the 911/988 system-prompt rule and kick off escalation
without waiting on it.
"""
import asyncio
import logging
import re
from dataclasses import dataclass

from app.events.outbox import emit_event
from app.providers.router import ProviderError, get_router

log = logging.getLogger(__name__)

INTENT_TIMEOUT_SECONDS = 1.5

_VALID_INTENTS = {"question", "smalltalk", "lead", "action", "complaint", "emergency", "off_scope"}
_VALID_SEVERITIES = {"critical", "high", "medium", "low"}

# Deliberately narrow: genuine life-safety language only. The broader
# escalation trigger categories (angry/churning customer, high-value
# lead, legal threat, payment fraud, owner-defined rules -- master
# prompt section H / launch/06-ESCALATION-DESIGN.md) belong to D5.3's
# rule engine, not this fast fallback path.
_EMERGENCY_PATTERNS = [
    r"\b(?:kill myself|suicid\w*|end my life|want to die|self[- ]harm)\b",
    r"\b(?:overdose|can'?t breathe|chest pain|heart attack|stroke)\b",
    r"\b(?:being attacked|someone is trying to hurt me|in danger right now)\b",
]

_SYSTEM_PROMPT = (
    'Classify the visitor message. Respond with JSON only: '
    '{"intent": "question|smalltalk|lead|action|complaint|emergency|off_scope", '
    '"severity": "critical|high|medium|low", "language": "<ISO 639-1 code>"}. '
    'severity="critical" ONLY for genuine life-safety emergencies (self-harm, medical emergency, '
    'immediate physical danger). Ordinary complaints are "medium" or "low", never "critical".'
)


@dataclass
class IntentResult:
    intent: str
    severity: str
    language: str
    source: str  # 'llm' | 'rules_fallback'


def _rules_fallback(text: str) -> IntentResult:
    if any(re.search(p, text, re.I) for p in _EMERGENCY_PATTERNS):
        return IntentResult(intent="emergency", severity="critical", language="en", source="rules_fallback")
    return IntentResult(intent="question", severity="low", language="en", source="rules_fallback")


async def classify_intent(conn, scope, text: str) -> IntentResult:
    try:
        router = get_router()
        result = await asyncio.wait_for(
            router.complete_json(
                [{"role": "system", "content": _SYSTEM_PROMPT}, {"role": "user", "content": text}],
                max_tokens=100,
            ),
            timeout=INTENT_TIMEOUT_SECONDS,
        )
        intent = result.get("intent")
        severity = result.get("severity")
        language = result.get("language") or "en"
        if intent not in _VALID_INTENTS or severity not in _VALID_SEVERITIES:
            raise ValueError("intent_response_shape_unexpected")
        classification = IntentResult(intent=intent, severity=severity, language=language, source="llm")
    except (asyncio.TimeoutError, ProviderError, ValueError, TypeError) as exc:
        log.warning("intent classification fell through to rules (%s)", exc)
        classification = _rules_fallback(text)

    if classification.severity == "critical" or classification.intent == "emergency":
        try:
            emit_event(
                conn,
                scope.company_id,
                "escalation.requested",
                {
                    "conversation_id": scope.conversation_id,
                    "severity": classification.severity,
                    "intent": classification.intent,
                    "reason": "emergency_language_detected",
                    "source": classification.source,
                },
                bot_id=scope.bot_id,
            )
        except Exception:  # noqa: BLE001 -- the turn must never fail because the escalation signal couldn't be queued
            log.exception("failed to emit escalation.requested event")

    return classification
