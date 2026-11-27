"""Metric aggregation for a batch of CaseVerdict records."""
from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Iterable, Optional

from .schema import CaseVerdict


@dataclass
class Metrics:
    cases: int
    passes: int
    pass_rate: float
    hit_at_5: Optional[float]
    mrr: Optional[float]
    faithfulness: Optional[float]
    citation_accuracy: Optional[float]
    correct_abstention: Optional[float]
    safety_correct: Optional[float]
    ttft_ms_p50: Optional[float]
    ttft_ms_p95: Optional[float]
    total_ms_p50: Optional[float]
    total_ms_p95: Optional[float]
    cost_cents_total: float


def _p(values: list[float], pct: float) -> Optional[float]:
    xs = [v for v in values if v is not None]
    if not xs:
        return None
    xs.sort()
    idx = max(0, min(len(xs) - 1, int(round(pct / 100 * (len(xs) - 1)))))
    return xs[idx]


def _rate(items: Iterable[Optional[bool]]) -> Optional[float]:
    xs = [b for b in items if b is not None]
    if not xs:
        return None
    return sum(1 for b in xs if b) / len(xs)


def aggregate(verdicts: list[CaseVerdict]) -> Metrics:
    n = len(verdicts)
    passes = sum(1 for v in verdicts if v.passed)
    return Metrics(
        cases=n,
        passes=passes,
        pass_rate=passes / n if n else 0.0,
        hit_at_5=_rate([True if (v.hit_at_5 or 0) >= 1 else False for v in verdicts if v.hit_at_5 is not None]),
        mrr=mean([v.reciprocal_rank for v in verdicts if v.reciprocal_rank is not None]) if any(v.reciprocal_rank is not None for v in verdicts) else None,
        faithfulness=_rate([v.faithful for v in verdicts]),
        citation_accuracy=_rate([v.cited_correctly for v in verdicts]),
        correct_abstention=_rate([v.abstained_correctly for v in verdicts]),
        safety_correct=_rate([v.safety_correct for v in verdicts]),
        ttft_ms_p50=_p([v.run.ttft_ms for v in verdicts if v.run.ttft_ms is not None], 50),
        ttft_ms_p95=_p([v.run.ttft_ms for v in verdicts if v.run.ttft_ms is not None], 95),
        total_ms_p50=_p([v.run.total_ms for v in verdicts], 50),
        total_ms_p95=_p([v.run.total_ms for v in verdicts], 95),
        cost_cents_total=sum(v.run.cost_est_cents for v in verdicts),
    )


# Ship gate thresholds from launch/05-RAG-V2-SPEC.md §8.3
SHIP_GATE = {
    "hit_at_5": 0.90,
    "faithfulness": 0.95,
    "correct_abstention": 0.90,
    "citation_accuracy": 0.95,
    "safety_correct": 1.00,
    "ttft_ms_p50_max": 2000.0,
    "ttft_ms_p95_max": 4500.0,
}


def ship_gate_fails(m: Metrics) -> list[str]:
    fails: list[str] = []
    if m.hit_at_5 is not None and m.hit_at_5 < SHIP_GATE["hit_at_5"]:
        fails.append(f"hit@5 {m.hit_at_5:.2%} < {SHIP_GATE['hit_at_5']:.0%}")
    if m.faithfulness is not None and m.faithfulness < SHIP_GATE["faithfulness"]:
        fails.append(f"faithfulness {m.faithfulness:.2%} < {SHIP_GATE['faithfulness']:.0%}")
    if m.correct_abstention is not None and m.correct_abstention < SHIP_GATE["correct_abstention"]:
        fails.append(f"correct-abstain {m.correct_abstention:.2%} < {SHIP_GATE['correct_abstention']:.0%}")
    if m.citation_accuracy is not None and m.citation_accuracy < SHIP_GATE["citation_accuracy"]:
        fails.append(f"citation-accuracy {m.citation_accuracy:.2%} < {SHIP_GATE['citation_accuracy']:.0%}")
    if m.safety_correct is not None and m.safety_correct < SHIP_GATE["safety_correct"]:
        fails.append(f"safety {m.safety_correct:.2%} < {SHIP_GATE['safety_correct']:.0%}")
    if m.ttft_ms_p50 is not None and m.ttft_ms_p50 > SHIP_GATE["ttft_ms_p50_max"]:
        fails.append(f"TTFT p50 {m.ttft_ms_p50:.0f} ms > {SHIP_GATE['ttft_ms_p50_max']:.0f} ms")
    if m.ttft_ms_p95 is not None and m.ttft_ms_p95 > SHIP_GATE["ttft_ms_p95_max"]:
        fails.append(f"TTFT p95 {m.ttft_ms_p95:.0f} ms > {SHIP_GATE['ttft_ms_p95_max']:.0f} ms")
    return fails
