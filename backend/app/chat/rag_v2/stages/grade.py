"""Grade stage (launch/05-RAG-V2-SPEC.md 3.6): LLM-judged sufficiency
check -- does the retrieved+reranked evidence actually answer the
question? The sufficiency LOOP (replace query with suggest_subquery,
redo retrieve+rerank, up to max_loop_iterations) lives in pipeline.py;
this module is the pure per-iteration judgment, same one-stage-one-file
shape as every other stage.
"""
import asyncio
import logging
from dataclasses import dataclass

from app.chat.rag_v2.base import Passage
from app.providers.router import ProviderError, get_router

log = logging.getLogger(__name__)

GRADE_TIMEOUT_SECONDS = 2.0

_SYSTEM_PROMPT = (
    "You judge whether the EVIDENCE below is sufficient to answer the QUESTION. "
    "Respond with JSON only: "
    '{"sufficient": true|false, "reason": "short reason", "suggest_subquery": "a better search query, or null"}. '
    "sufficient=false only if the evidence is clearly missing information the question needs -- "
    "don't require exhaustive coverage of every detail."
)


@dataclass
class GradeResult:
    sufficient: bool
    reason: str
    suggest_subquery: str | None


def _format_evidence(passages: list[Passage]) -> str:
    return "\n\n".join(f"[{i + 1}] {p.title}: {p.text}" for i, p in enumerate(passages))


async def grade_sufficiency(question: str, passages: list[Passage]) -> GradeResult:
    """Fails open (sufficient=True) on any provider failure or timeout --
    a missed opportunity to loop once more is far less harmful than
    stalling the whole turn on a grading call that can't complete."""
    if not passages:
        return GradeResult(sufficient=False, reason="no_evidence_retrieved", suggest_subquery=None)

    try:
        router = get_router()
        result = await asyncio.wait_for(
            router.complete_json(
                [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": f"EVIDENCE:\n{_format_evidence(passages)}\n\nQUESTION:\n{question}"},
                ],
                max_tokens=200,
            ),
            timeout=GRADE_TIMEOUT_SECONDS,
        )
        sufficient = result.get("sufficient")
        if not isinstance(sufficient, bool):
            raise ValueError("grade_response_shape_unexpected")
        return GradeResult(
            sufficient=sufficient,
            reason=str(result.get("reason") or ""),
            suggest_subquery=result.get("suggest_subquery") or None,
        )
    except (asyncio.TimeoutError, ProviderError, ValueError, TypeError) as exc:
        log.warning("grade fell through to sufficient=True (%s)", exc)
        return GradeResult(sufficient=True, reason="grader_unavailable", suggest_subquery=None)
