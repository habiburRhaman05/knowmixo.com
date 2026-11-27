"""HTTP Actions API (D5.2): CRUD + test button for owner-defined webhook actions."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.actions import service
from app.auth.service import SessionPrincipal
from app.deps import get_verified_principal
from app.security.ssrf_http import SSRFBlocked

router = APIRouter(prefix="/api/v1/actions", tags=["actions"])


class ActionCreate(BaseModel):
    bot_id: str
    name: str = Field(..., max_length=200)
    description: str = Field(default="", max_length=1000)
    method: str = Field(default="POST", pattern="^(GET|POST|PUT|PATCH|DELETE)$")
    url: str = Field(..., max_length=2000)
    headers: dict | None = None
    body_template: dict | None = None
    timeout_ms: int = Field(default=5000, ge=500, le=30000)


class ActionUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=1000)
    method: str | None = Field(default=None, pattern="^(GET|POST|PUT|PATCH|DELETE)$")
    url: str | None = Field(default=None, max_length=2000)
    headers: dict | None = None
    body_template: dict | None = None
    timeout_ms: int | None = Field(default=None, ge=500, le=30000)
    active: bool | None = None


@router.post("")
async def create_action(body: ActionCreate, principal: SessionPrincipal = Depends(get_verified_principal)):
    try:
        action = service.create_action(
            principal.company_id, body.bot_id,
            name=body.name, url=body.url, method=body.method,
            headers=body.headers, body_template=body.body_template,
            description=body.description, timeout_ms=body.timeout_ms,
        )
        return action
    except SSRFBlocked as exc:
        raise HTTPException(400, detail={"code": "url_blocked", "message": str(exc)})


@router.get("")
async def list_actions(bot_id: str | None = None, principal: SessionPrincipal = Depends(get_verified_principal)):
    return service.list_actions(principal.company_id, bot_id)


@router.get("/{action_id}")
async def get_action(action_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    action = service.get_action(principal.company_id, action_id)
    if not action:
        raise HTTPException(404, detail={"code": "action_not_found", "message": "Action not found."})
    return action


@router.patch("/{action_id}")
async def update_action(action_id: str, body: ActionUpdate, principal: SessionPrincipal = Depends(get_verified_principal)):
    updates = body.model_dump(exclude_unset=True)
    try:
        result = service.update_action(principal.company_id, action_id, **updates)
    except SSRFBlocked as exc:
        raise HTTPException(400, detail={"code": "url_blocked", "message": str(exc)})
    if not result:
        raise HTTPException(404, detail={"code": "action_not_found", "message": "Action not found."})
    return result


@router.delete("/{action_id}")
async def delete_action(action_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    if not service.delete_action(principal.company_id, action_id):
        raise HTTPException(404, detail={"code": "action_not_found", "message": "Action not found."})
    return {"deleted": True}


@router.post("/{action_id}/test")
async def test_action(action_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    result = await service.test_action(principal.company_id, action_id)
    return result
