"""Verify stage (launch/05-RAG-V2-SPEC.md 3.8): faithfulness check.
LLM judges whether the generated answer's claims are supported by the
cited passages. If not faithful after one regeneration retry, the
pipeline abstains instead of streaming a hallucinated answer.
"""
import asyncio
import logging
from dataclasses import dataclass, field

from app.chat.rag_v2.base import Passage
from app.providers.router import ProviderError, get_router

log = logging.getLogger(__name__)

VERIFY_TIMEOUT_SECONDS = 3.0

_SYSTEM_PROMPT = (
    "You are a faithfulness verifier. Given EVIDENCE passages and an ANSWER, "
    "decide if every factual claim in the answer is supported by the evidence. "
    "Respond with JSON only: "
    '{"faithful": true|false, "unsupported_claims": ["claim text", ...]}. '
    "An empty unsupported_claims list means faithful=true."
)


@dataclass
class VerifyResult:
    faithful: bool
    unsupported_claims: list[str] = field(default_factory=list)


def _format_evidence(passages: list[Passage]) -> str:
    return "\n\n".join(f"[{i + 1}] {p.title}: {p.text}" for i, p in enumerate(passages))


async def verify_faithfulness(answer: str, passages: list[Passage]) -> VerifyResult:
    """Returns VerifyResult. Fails open (faithful=True) on provider
    errors or timeouts -- better to serve a possibly-unfaithful answer
    than block the whole turn on a verifier that can't respond."""
    if not answer or not passages:
        return VerifyResult(faithful=True)

    try:
        router = get_router()
        result = await asyncio.wait_for(
            router.complete_json(
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"EVIDENCE:\n{_format_evidence(passages)}\n\n"
                            f"ANSWER:\n{answer}"
                        ),
                    },
                ],
                max_tokens=300,
            ),
            timeout=VERIFY_TIMEOUT_SECONDS,
        )
        faithful = result.get("faithful")
        if not isinstance(faithful, bool):
            raise ValueError("verify_response_shape_unexpected")
        claims = result.get("unsupported_claims") or []
        if not isinstance(claims, list):
            claims = []
        return VerifyResult(
            faithful=faithful,
            unsupported_claims=[str(c) for c in claims],
        )
    except (asyncio.TimeoutError, ProviderError, ValueError, TypeError) as exc:
        log.warning("verify fell through to faithful=True (%s)", exc)
        return VerifyResult(faithful=True)
