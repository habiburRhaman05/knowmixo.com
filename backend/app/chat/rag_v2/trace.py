"""Write a rag_traces row after each v2 turn completes (or fails).
The trace table was created by migration 0019 and mirrors the DDL in
launch/05-RAG-V2-SPEC.md section 6.
"""
import json
import logging

log = logging.getLogger(__name__)


def write_trace(
    conn,
    *,
    company_id: str,
    conversation_id: str,
    message_id: str,
    intent: str | None = None,
    severity: str | None = None,
    language: str | None = None,
    rewritten_queries: list[str] | None = None,
    retrieved: list[dict] | None = None,
    reranked: list[dict] | None = None,
    grade_iterations: int = 0,
    tools_used: list[str] | None = None,
    verifier_result: dict | None = None,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    latency_ms_total: int = 0,
    latency_ms_per_stage: dict | None = None,
    provider: str | None = None,
    model: str | None = None,
    cost_est_cents: float | None = None,
    abstained: bool = False,
    escalated: bool = False,
) -> str | None:
    try:
        row = conn.execute(
            """
            INSERT INTO rag_traces (
                company_id, conversation_id, message_id,
                intent, severity, language,
                rewritten_queries, retrieved, reranked,
                grade_iterations, tools_used, verifier_result,
                tokens_in, tokens_out,
                latency_ms_total, latency_ms_per_stage,
                provider, model, cost_est_cents,
                abstained, escalated
            ) VALUES (
                %s, %s, %s,
                %s, %s, %s,
                %s::jsonb, %s::jsonb, %s::jsonb,
                %s, %s::jsonb, %s::jsonb,
                %s, %s,
                %s, %s::jsonb,
                %s, %s, %s,
                %s, %s
            ) RETURNING id
            """,
            (
                company_id, conversation_id, message_id,
                intent, severity, language,
                json.dumps(rewritten_queries or []),
                json.dumps(retrieved or []),
                json.dumps(reranked or []),
                grade_iterations,
                json.dumps(tools_used or []),
                json.dumps(verifier_result) if verifier_result else None,
                tokens_in, tokens_out,
                latency_ms_total,
                json.dumps(latency_ms_per_stage or {}),
                provider, model, cost_est_cents,
                abstained, escalated,
            ),
        ).fetchone()
        return str(row["id"]) if row else None
    except Exception:
        log.exception("failed to write rag_trace")
        return None
