"""Gaps + bad-answers queue API (D8.3)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.service import SessionPrincipal
from app.db import connection
from app.deps import get_verified_principal
from app.quality import bad_answers, gaps

router = APIRouter(prefix="/api/v1/quality", tags=["quality"])


# --- Gaps -------------------------------------------------------------------


class ResolveGapRequest(BaseModel):
    answer: str = Field(..., min_length=1, max_length=5000)


@router.get("/gaps")
async def list_gaps(status: str = "open", principal: SessionPrincipal = Depends(get_verified_principal)):
    if status not in ("open", "resolved", "ignored"):
        raise HTTPException(422, detail={"code": "invalid_status", "message": "status must be open, resolved, or ignored."})
    return gaps.list_gaps(principal.company_id, status)


@router.post("/gaps/recompute")
async def recompute_gaps(principal: SessionPrincipal = Depends(get_verified_principal)):
    with connection() as conn:
        bots = conn.execute("SELECT id FROM bots WHERE company_id = %s", (principal.company_id,)).fetchall()
    total = sum(gaps.recompute_gaps(principal.company_id, str(b["id"])) for b in bots)
    return {"clusters_touched": total}


@router.post("/gaps/{gap_id}/resolve")
async def resolve_gap(gap_id: str, body: ResolveGapRequest, principal: SessionPrincipal = Depends(get_verified_principal)):
    try:
        return gaps.resolve_gap(principal.company_id, gap_id, principal.user_id, body.answer)
    except gaps.GapError as exc:
        raise HTTPException(exc.status_code, detail={"code": exc.code, "message": exc.message})


@router.post("/gaps/{gap_id}/ignore")
async def ignore_gap(gap_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    if not gaps.ignore_gap(principal.company_id, gap_id):
        raise HTTPException(404, detail={"code": "gap_not_found", "message": "Gap not found."})
    return {"ignored": True}


# --- Bad answers --------------------------------------------------------


class CorrectAnswerRequest(BaseModel):
    correction_text: str = Field(..., min_length=1, max_length=5000)


@router.get("/bad-answers")
async def list_bad_answers(principal: SessionPrincipal = Depends(get_verified_principal)):
    return bad_answers.list_queue(principal.company_id)


@router.get("/bad-answers/{message_id}")
async def get_bad_answer(message_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    detail = bad_answers.get_detail(principal.company_id, message_id)
    if not detail:
        raise HTTPException(404, detail={"code": "message_not_found", "message": "Message not found."})
    return detail


@router.post("/bad-answers/{message_id}/correct")
async def correct_answer(message_id: str, body: CorrectAnswerRequest, principal: SessionPrincipal = Depends(get_verified_principal)):
    try:
        return bad_answers.correct_answer(principal.company_id, message_id, principal.user_id, body.correction_text)
    except bad_answers.BadAnswerError as exc:
        raise HTTPException(exc.status_code, detail={"code": exc.code, "message": exc.message})


@router.post("/bad-answers/{message_id}/dismiss")
async def dismiss_bad_answer(message_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    try:
        bad_answers.dismiss(principal.company_id, message_id)
    except bad_answers.BadAnswerError as exc:
        raise HTTPException(exc.status_code, detail={"code": exc.code, "message": exc.message})
    return {"dismissed": True}
