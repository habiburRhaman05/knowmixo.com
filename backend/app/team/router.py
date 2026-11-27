"""Team members + invites API (D8.6)."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.auth.service import SessionPrincipal
from app.db import connection
from app.deps import get_verified_principal, require_role
from app.team import service

router = APIRouter(prefix="/api/v1/team", tags=["team"])
public_router = APIRouter(prefix="/api/v1/team", tags=["team"])


def _raise(exc: service.TeamError):
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


class InviteCreate(BaseModel):
    email: EmailStr
    role: str = Field(..., pattern="^(admin|agent|viewer)$")


class RoleUpdate(BaseModel):
    role: str = Field(..., pattern="^(admin|agent|viewer)$")


class AcceptInviteRequest(BaseModel):
    token: str
    name: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, min_length=8, max_length=200)


@router.get("/members")
async def list_members(principal: SessionPrincipal = Depends(get_verified_principal)):
    with connection() as conn:
        return service.list_members(conn, principal.company_id)


@router.patch("/members/{user_id}")
async def update_member_role(user_id: str, body: RoleUpdate, principal: SessionPrincipal = Depends(require_role("owner", "admin"))):
    try:
        with connection() as conn:
            return service.update_member_role(conn, principal.company_id, user_id, body.role)
    except service.TeamError as exc:
        _raise(exc)


@router.delete("/members/{user_id}")
async def remove_member(user_id: str, principal: SessionPrincipal = Depends(require_role("owner", "admin"))):
    try:
        with connection() as conn:
            service.remove_member(conn, principal.company_id, user_id)
    except service.TeamError as exc:
        _raise(exc)
    return {"removed": True}


@router.post("/invites")
async def create_invite(body: InviteCreate, principal: SessionPrincipal = Depends(require_role("owner", "admin"))):
    try:
        with connection() as conn:
            return service.create_invite(conn, principal.company_id, principal.user_id, body.email, body.role)
    except service.TeamError as exc:
        _raise(exc)


@router.get("/invites")
async def list_invites(principal: SessionPrincipal = Depends(require_role("owner", "admin"))):
    with connection() as conn:
        return service.list_invites(conn, principal.company_id)


@router.delete("/invites/{invite_id}")
async def revoke_invite(invite_id: str, principal: SessionPrincipal = Depends(require_role("owner", "admin"))):
    with connection() as conn:
        if not service.revoke_invite(conn, principal.company_id, invite_id):
            raise HTTPException(404, detail={"code": "invite_not_found", "message": "Invite not found or already used."})
    return {"revoked": True}


@public_router.get("/invites/{token}")
async def preview_invite(token: str):
    """Public, token-authenticated: lets the accept-invite page show which
    company/role before the invitee commits to creating an account."""
    with connection() as conn:
        invite = service.resolve_invite(conn, token)
    if not invite:
        raise HTTPException(410, detail={"code": "invite_expired", "message": "This invite has expired, was revoked, or was already used."})
    return {"email": invite["email"], "role": invite["role"], "company_name": invite["company_name"]}


@public_router.post("/invites/accept")
async def accept_invite(body: AcceptInviteRequest):
    try:
        with connection() as conn:
            session_token = service.accept_invite(conn, body.token, body.name or "", body.password or "")
    except service.TeamError as exc:
        _raise(exc)
    return {"session_token": session_token}
