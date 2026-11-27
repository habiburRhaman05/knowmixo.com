"""Human-readable eval report."""
from __future__ import annotations

from datetime import datetime, timezone

from .metrics import Metrics
from .schema import CaseVerdict


def render(config: str, verdicts: list[CaseVerdict], metrics: Metrics, baseline: Metrics | None = None) -> str:
    lines: list[str] = []
    lines.append(f"# RAG eval — {config}")
    lines.append("")
    lines.append(f"Run at: {datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("## Headline")
    lines.append("")

    def pct(v: float | None) -> str:
        return "—" if v is None else f"{v:.2%}"

    def ms(v: float | None) -> str:
        return "—" if v is None else f"{v:.0f} ms"

    headers = ["Metric", config]
    if baseline:
        headers.append("baseline")
        headers.append("Δ")
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

    def row(name: str, current, prior, formatter):
        cells = [name, formatter(current)]
        if baseline is not None:
            cells.append(formatter(prior))
            if current is None or prior is None:
                cells.append("—")
            else:
                diff = current - prior
                sign = "+" if diff >= 0 else ""
                cells.append(sign + formatter(diff) if callable(formatter) else str(diff))
        lines.append("| " + " | ".join(cells) + " |")

    row("Cases", metrics.cases, baseline.cases if baseline else None, lambda v: str(v) if v is not None else "—")
    row("Pass rate", metrics.pass_rate, baseline.pass_rate if baseline else None, pct)
    row("Hit@5", metrics.hit_at_5, baseline.hit_at_5 if baseline else None, pct)
    row("MRR@10", metrics.mrr, baseline.mrr if baseline else None, lambda v: "—" if v is None else f"{v:.3f}")
    row("Faithfulness", metrics.faithfulness, baseline.faithfulness if baseline else None, pct)
    row("Citation accuracy", metrics.citation_accuracy, baseline.citation_accuracy if baseline else None, pct)
    row("Correct abstention", metrics.correct_abstention, baseline.correct_abstention if baseline else None, pct)
    row("Safety correctness", metrics.safety_correct, baseline.safety_correct if baseline else None, pct)
    row("TTFT p50", metrics.ttft_ms_p50, baseline.ttft_ms_p50 if baseline else None, ms)
    row("TTFT p95", metrics.ttft_ms_p95, baseline.ttft_ms_p95 if baseline else None, ms)
    row("Total p50", metrics.total_ms_p50, baseline.total_ms_p50 if baseline else None, ms)
    row("Total p95", metrics.total_ms_p95, baseline.total_ms_p95 if baseline else None, ms)
    row("Cost (cents)", metrics.cost_cents_total, baseline.cost_cents_total if baseline else None, lambda v: "—" if v is None else f"{v:.2f}")

    lines.append("")
    lines.append("## Per-case verdicts")
    lines.append("")
    lines.append("| Bucket | ID | Expected | Status | Pass | Reasons |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for v in verdicts:
        lines.append(
            "| {bucket} | {id} | {kind} | {status} | {passed} | {reasons} |".format(
                bucket=v.case.bucket,
                id=v.case.id,
                kind=v.case.expected_kind,
                status=v.run.status,
                passed="✅" if v.passed else "❌",
                reasons="; ".join(v.reasons_failed) if v.reasons_failed else "—",
            )
        )

    return "\n".join(lines) + "\n"
