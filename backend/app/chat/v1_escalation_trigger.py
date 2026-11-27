"""Minimal v1-side escalation trigger.

The full escalation detector (app.escalation.detector.detect_and_create)
is only ever called from app.chat.tools.escalate_to_human (LLM
tool-calling) and rag_v2/stages/intent.py's regex fast-path -- both
belong to the v2/tools pipeline, which the 2026-11-27 launch decision
keeps dark (`settings().rag_engine == "v1"`). Without this module, a
real visitor message suggesting a safety emergency or a demand for a
human would never create an escalations row or notify anyone under v1 --
only the system prompt's own 911/988 text reply (app.chat.llm) would
fire.

This ports just the cheapest part of the v2 design
(launch/06-ESCALATION-DESIGN.md §2.1 "visitor explicit": a keyword/regex
match, no classifier or LLM call) into v1, so a real signal still pages
a human at launch. It intentionally does not replicate owner rules
(F.2) or behavioral triggers (F.1's abstention/thumbs-down signals) --
those stay v2-only.
"""
import re

_SAFETY_PATTERNS = [
    r"\bkill (myself|me)\b",
    r"\bsuicid\w*\b",
    r"\bwant(ed)? to die\b",
    r"\bend(ing)? (my life|it all)\b",
    r"\b(hurt|harm) (myself|me)\b",
    r"\bself[- ]harm\b",
    r"\bover ?dose\b",
    r"\bin (immediate )?danger\b",
    r"\bmedical emergency\b",
]

_ACTION_PATTERNS = [
    r"\burgent(ly)?\b",
    r"\bneed (a|to (talk|speak) to) (a )?human\b",
    r"\b(talk|speak) to (a )?(human|person|agent|someone)\b",
    r"\blawyer\b",
    r"\battorney\b",
    r"\bchargeback\b",
    r"\brefund( me)? now\b",
    r"\bcancel (my )?(account|subscription|order)\b",
]

_SAFETY_RE = re.compile("|".join(_SAFETY_PATTERNS), re.IGNORECASE)
_ACTION_RE = re.compile("|".join(_ACTION_PATTERNS), re.IGNORECASE)


def detect(text: str) -> tuple[str, str, str] | None:
    """Returns (severity, intent, reason) on a match, else None. Safety
    patterns win over action patterns when both match the same message."""
    if _SAFETY_RE.search(text):
        return "critical", "emergency", "Visitor's message suggests a possible safety emergency"
    if _ACTION_RE.search(text):
        return "high", "action", "Visitor's message suggests they want a human"
    return None
