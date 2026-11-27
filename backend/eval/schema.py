"""Typed records shared across the eval harness."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal, Optional


@dataclass
class GoldenCase:
    """One row in a golden set JSONL file.

    bucket        — folder under eval/golden/, e.g. 'en/general', 'injection'
    id            — stable short id for the row; used in reports
    question      — visitor prompt
    history       — prior turns if any ([{role, content}])
    expected_kind — 'answerable' | 'abstention' | 'clarify' | 'safety'
    expected_sources — list of source chunk_ids that MUST appear in the top-k
                       retrieved results (used for hit@k + MRR)
    expected_answer_substrings — optional list; each must appear case-insensitively
    forbidden_substrings — list of things the answer must not contain
                           (e.g. the system prompt leaking)
    safety_phrases — for emergency bucket, the required safety text
    language      — ISO 639-1; default en
    """

    bucket: str
    id: str
    question: str
    expected_kind: Literal["answerable", "abstention", "clarify", "safety"]
    history: list[dict] = field(default_factory=list)
    expected_sources: list[str] = field(default_factory=list)
    expected_answer_substrings: list[str] = field(default_factory=list)
    forbidden_substrings: list[str] = field(default_factory=list)
    safety_phrases: list[str] = field(default_factory=list)
    language: str = "en"

    @classmethod
    def from_dict(cls, data: dict) -> "GoldenCase":
        return cls(
            bucket=data["bucket"],
            id=data["id"],
            question=data["question"],
            expected_kind=data["expected_kind"],
            history=data.get("history", []),
            expected_sources=data.get("expected_sources", []),
            expected_answer_substrings=data.get("expected_answer_substrings", []),
            forbidden_substrings=data.get("forbidden_substrings", []),
            safety_phrases=data.get("safety_phrases", []),
            language=data.get("language", "en"),
        )


@dataclass
class StageTiming:
    stage: str
    ms: float


@dataclass
class TurnRun:
    """What the pipeline produced for one golden case."""

    case_id: str
    config: str
    status: Literal["completed", "abstained", "failed"]
    answer: str
    retrieved_ids: list[str]
    reranked_ids: list[str]
    cited_ids: list[str]
    ttft_ms: Optional[float]
    total_ms: float
    tokens_in: int
    tokens_out: int
    provider: str
    model: str
    error_code: Optional[str] = None
    cost_est_cents: float = 0.0
    stage_timings: list[StageTiming] = field(default_factory=list)


@dataclass
class CaseVerdict:
    case: GoldenCase
    run: TurnRun
    passed: bool
    reasons_failed: list[str] = field(default_factory=list)
    # Retrieval-side numeric metrics for aggregation
    hit_at_5: Optional[float] = None
    reciprocal_rank: Optional[float] = None
    # Generation-side
    faithful: Optional[bool] = None
    cited_correctly: Optional[bool] = None
    abstained_correctly: Optional[bool] = None
    safety_correct: Optional[bool] = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d
