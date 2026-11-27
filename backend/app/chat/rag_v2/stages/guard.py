"""Guard stage (launch/05-RAG-V2-SPEC.md 3.1): input safety +
prompt-injection, reusing app/guardrails.py's regex rather than a second
implementation. Adds the length/empty/encoding checks the spec calls
for on top of that shared regex set.
"""
import unicodedata

from app.chat.rag_v2.errors import InputBlocked
from app.guardrails import classify_input

MAX_MESSAGE_CHARS = 4000


def guard_input(text: str) -> str:
    """Returns the normalised text, or raises InputBlocked. Normalisation
    (NFKC) happens before the guardrail regex runs, so a visually-similar
    unicode lookalike can't slip an injection pattern past it."""
    normalized = unicodedata.normalize("NFKC", text or "").strip()
    if not normalized:
        raise InputBlocked("Message cannot be empty.")
    if len(normalized) > MAX_MESSAGE_CHARS:
        raise InputBlocked(f"Message must be {MAX_MESSAGE_CHARS} characters or fewer.")
    reason = classify_input(normalized)
    if reason:
        raise InputBlocked("This message was blocked by input guardrails.")
    return normalized
