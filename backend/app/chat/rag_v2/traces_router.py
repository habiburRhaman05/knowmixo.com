"""Playground retrieval inspector API (D7.5, launch/05-RAG-V2-SPEC.md §6):
read-only access to rag_traces for the owner dashboard. One row per v2
pipeline turn -- intent/severity/language, rewritten queries, retrieved
vs. reranked passages, grade loop iterations, verifier result, timing
per stage, and cost. Only populated for turns that ran under
rag_engine='v2'; empty under v1.
"""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.service import SessionPrincipal
from app.db import connection
from app.deps import get_verified_principal

router = APIRouter(prefix="/api/v1/rag-traces", tags=["rag-traces"])

_LIST_FIELDS = "id, conversation_id, message_id, intent, severity, language, grade_iterations, latency_ms_total, abstained, escalated, created_at"
_DETAIL_FIELDS = (
    "id, conversation_id, message_id, intent, severity, language, rewritten_queries, retrieved, "
    "reranked, grade_iterations, tools_used, verifier_result, tokens_in, tokens_out, "
    "latency_ms_total, latency_ms_per_stage, provider, model, cost_est_cents, abstained, escalated, created_at"
)


@router.get("")
async def list_traces(
    conversation_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    principal: SessionPrincipal = Depends(get_verified_principal),
):
    with connection() as conn:
        if conversation_id:
            rows = conn.execute(
                f"SELECT {_LIST_FIELDS} FROM rag_traces WHERE company_id = %s AND conversation_id = %s ORDER BY created_at DESC LIMIT %s",
                (principal.company_id, conversation_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {_LIST_FIELDS} FROM rag_traces WHERE company_id = %s ORDER BY created_at DESC LIMIT %s",
                (principal.company_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]


@router.get("/{trace_id}")
async def get_trace(trace_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    with connection() as conn:
        row = conn.execute(
            f"SELECT {_DETAIL_FIELDS} FROM rag_traces WHERE id = %s AND company_id = %s",
            (trace_id, principal.company_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, detail={"code": "trace_not_found", "message": "Trace not found."})
    return dict(row)


@router.get("/by-message/{message_id}")
async def get_trace_by_message(message_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    with connection() as conn:
        row = conn.execute(
            f"SELECT {_DETAIL_FIELDS} FROM rag_traces WHERE message_id = %s AND company_id = %s",
            (message_id, principal.company_id),
        ).fetchone()
    if not row:
        raise HTTPException(404, detail={"code": "trace_not_found", "message": "No trace recorded for this message."})
    return dict(row)
