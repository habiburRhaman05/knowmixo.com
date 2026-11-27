"""Handoff API (D5.5): conversation status management, assignment, canned replies."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.service import SessionPrincipal
from app.deps import get_verified_principal
from app.handoff import service

router = APIRouter(prefix="/api/v1/handoff", tags=["handoff"])


class HandoffRequest(BaseModel):
    conversation_id: str
    assigned_to: str | None = None


class AssignRequest(BaseModel):
    conversation_id: str
    user_id: str


class CannedReplyCreate(BaseModel):
    title: str = Field(..., max_length=200)
    body: str = Field(..., max_length=5000)
    shortcut: str | None = Field(default=None, max_length=50)


class CannedReplyUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    body: str | None = Field(default=None, max_length=5000)
    shortcut: str | None = Field(default=None, max_length=50)
    sort_order: int | None = None
    active: bool | None = None


class ReplyRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)


@router.post("/take")
async def take_over(body: HandoffRequest, principal: SessionPrincipal = Depends(get_verified_principal)):
    result = service.hand_off(principal.company_id, body.conversation_id, body.assigned_to or principal.user_id)
    if "error" in result:
        raise HTTPException(404, detail={"code": "conversation_not_found", "message": result["error"]})
    return result


@router.post("/{conversation_id}/reply")
async def reply(conversation_id: str, body: ReplyRequest, principal: SessionPrincipal = Depends(get_verified_principal)):
    try:
        return service.send_agent_reply(principal.company_id, conversation_id, body.text, principal.user_id)
    except service.HandoffError as exc:
        raise HTTPException(exc.status_code, detail={"code": exc.code, "message": exc.message})


@router.post("/assign")
async def assign(body: AssignRequest, principal: SessionPrincipal = Depends(get_verified_principal)):
    result = service.assign(principal.company_id, body.conversation_id, body.user_id)
    if "error" in result:
        raise HTTPException(404, detail={"code": "conversation_not_found", "message": result["error"]})
    return result


@router.post("/{conversation_id}/resolve")
async def resolve(conversation_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    result = service.resolve(principal.company_id, conversation_id)
    if "error" in result:
        raise HTTPException(404, detail={"code": "conversation_not_found", "message": result["error"]})
    return result


@router.post("/{conversation_id}/return-to-bot")
async def return_to_bot(conversation_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    result = service.return_to_bot(principal.company_id, conversation_id)
    if "error" in result:
        raise HTTPException(404, detail={"code": "conversation_not_found", "message": result["error"]})
    return result


@router.get("/queue")
async def list_queue(principal: SessionPrincipal = Depends(get_verified_principal)):
    return service.list_queued(principal.company_id)


# --- Canned replies ---

@router.post("/canned-replies")
async def create_canned_reply(body: CannedReplyCreate, principal: SessionPrincipal = Depends(get_verified_principal)):
    return service.create_canned_reply(principal.company_id, body.title, body.body, body.shortcut)


@router.get("/canned-replies")
async def list_canned_replies(principal: SessionPrincipal = Depends(get_verified_principal)):
    return service.list_canned_replies(principal.company_id)


@router.patch("/canned-replies/{reply_id}")
async def update_canned_reply(reply_id: str, body: CannedReplyUpdate, principal: SessionPrincipal = Depends(get_verified_principal)):
    updates = body.model_dump(exclude_unset=True)
    result = service.update_canned_reply(principal.company_id, reply_id, **updates)
    if not result:
        raise HTTPException(404, detail={"code": "reply_not_found", "message": "Canned reply not found."})
    return result


@router.delete("/canned-replies/{reply_id}")
async def delete_canned_reply(reply_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    if not service.delete_canned_reply(principal.company_id, reply_id):
        raise HTTPException(404, detail={"code": "reply_not_found", "message": "Canned reply not found."})
    return {"deleted": True}
