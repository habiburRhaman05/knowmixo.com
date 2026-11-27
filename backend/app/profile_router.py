"""Profile/company/account-lifecycle routes for Phase 1.

Full Epic B scope (avatar upload, data export) lands with Sprint 5 per
docs/15-USER-STORIES.md -- but email change, Google account linking, and
account deletion are identity-layer features with no dependency on
documents/bots, so they are completed here rather than left half-built.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.auth import service
from app.auth.service import AuthError, SessionPrincipal, get_company_for_owner, get_user_by_id
from app.db import connection
from app.deps import get_current_principal, require_step_up
from app.security.google_oauth import GoogleTokenError, verify_google_id_token

router = APIRouter(prefix="/api/v1", tags=["profile"])


def _raise(exc: AuthError):
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


@router.get("/me")
def get_me(principal: SessionPrincipal = Depends(get_current_principal)):
    with connection() as conn:
        user = get_user_by_id(conn, principal.user_id)
    return {
        "id": str(user["id"]),
        "email": user["email"],
        "name": user["name"],
        "avatar_key": user["avatar_key"],
        "email_verified_at": user["email_verified_at"],
    }


class EmailChangeRequest(BaseModel):
    new_email: EmailStr
    current_password: str | None = None


class EmailChangeConfirm(BaseModel):
    token: str


class GoogleLinkRequest(BaseModel):
    id_token: str = Field(min_length=10)


class DeleteAccountRequest(BaseModel):
    confirm: bool
    current_password: str | None = None


@router.post("/me/email-change", status_code=202)
def request_email_change(body: EmailChangeRequest, principal: SessionPrincipal = Depends(get_current_principal)):
    try:
        with connection() as conn:
            service.request_email_change(conn, principal.user_id, body.new_email, body.current_password)
    except AuthError as exc:
        _raise(exc)
    return {"status": "accepted"}


@router.post("/me/email-change/confirm")
def confirm_email_change(body: EmailChangeConfirm):
    try:
        with connection() as conn:
            service.confirm_email_change(conn, body.token)
    except AuthError as exc:
        _raise(exc)
    return {"status": "accepted"}


@router.post("/me/oauth/google/link")
def link_google(body: GoogleLinkRequest, principal: SessionPrincipal = Depends(get_current_principal)):
    try:
        claims = verify_google_id_token(body.id_token)
    except GoogleTokenError as exc:
        raise HTTPException(status_code=401, detail={"code": "invalid_google_token", "message": str(exc)})

    try:
        with connection() as conn:
            service.link_google_account(conn, principal.user_id, claims)
    except AuthError as exc:
        _raise(exc)
    return {"status": "linked"}


@router.delete("/me", status_code=202)
def delete_account(body: DeleteAccountRequest, principal: SessionPrincipal = Depends(require_step_up)):
    if not body.confirm:
        raise HTTPException(status_code=400, detail={"code": "confirmation_required", "message": "Set confirm=true to delete your account."})
    try:
        with connection() as conn:
            job_id = service.delete_account(conn, principal.user_id, body.current_password)
    except AuthError as exc:
        _raise(exc)
    return {
        "status": "deleted",
        "cleanup_job_id": job_id,
        "cleanup_status_url": f"/api/v1/jobs/{job_id}" if job_id else None,
        "note": "Sessions and public access were revoked immediately; vector and data cleanup runs as a background job.",
    }


_KEY_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_./-]*$"  # opaque storage key; no leading slash


class CompanyPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    website: str | None = None
    industry: str | None = None
    contact: str | None = None
    logo_key: str | None = Field(default=None, max_length=200, pattern=_KEY_PATTERN)


@router.get("/company")
def get_company(principal: SessionPrincipal = Depends(get_current_principal)):
    with connection() as conn:
        company = get_company_for_owner(conn, principal.user_id)
    if not company:
        raise HTTPException(status_code=404, detail={"code": "no_company", "message": "No company found."})
    return {
        "id": str(company["id"]),
        "name": company["name"],
        "website": company["website"],
        "industry": company["industry"],
        "contact": company["contact"],
        "logo_key": company["logo_key"],
    }


@router.patch("/company")
def patch_company(body: CompanyPatch, principal: SessionPrincipal = Depends(get_current_principal)):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        return {"status": "no_changes"}

    set_clause = ", ".join(f"{key} = %s" for key in fields)
    values = list(fields.values())

    with connection() as conn:
        row = conn.execute(
            f"""
            UPDATE companies SET {set_clause}, updated_at = now()
            WHERE owner_user_id = %s AND deleted_at IS NULL
            RETURNING id
            """,
            (*values, principal.user_id),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail={"code": "no_company", "message": "No company found."})
    return {"status": "updated"}


class MePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    avatar_key: str | None = Field(default=None, max_length=200, pattern=_KEY_PATTERN)


@router.patch("/me")
def patch_me(body: MePatch, principal: SessionPrincipal = Depends(get_current_principal)):
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    if not fields:
        return {"status": "no_changes"}
    if ".." in (fields.get("avatar_key") or ""):
        raise HTTPException(status_code=422, detail={"code": "invalid_avatar_key", "message": "Invalid avatar key."})
    set_clause = ", ".join(f"{key} = %s" for key in fields)
    with connection() as conn:
        conn.execute(
            f"UPDATE users SET {set_clause}, updated_at = now() WHERE id = %s",
            (*fields.values(), principal.user_id),
        )
    return {"status": "updated"}


class CompanyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    industry: str | None = None
    website: str | None = None


@router.post("/company", status_code=201)
def create_company(body: CompanyCreate, principal: SessionPrincipal = Depends(get_current_principal)):
    """V1: exactly one company per owner, auto-provisioned at signup. A
    second create is a 409 rather than a silent duplicate."""
    with connection() as conn:
        if get_company_for_owner(conn, principal.user_id):
            raise HTTPException(status_code=409, detail={"code": "company_exists", "message": "A company already exists for this account."})
        company = conn.execute(
            "INSERT INTO companies (owner_user_id, name, industry, website) VALUES (%s, %s, %s, %s) RETURNING id",
            (principal.user_id, body.name, body.industry, body.website),
        ).fetchone()
        conn.execute(
            "INSERT INTO memberships (company_id, user_id, role) VALUES (%s, %s, 'owner')",
            (company["id"], principal.user_id),
        )
    return {"id": str(company["id"])}


@router.get("/company/export")
def export_company(principal: SessionPrincipal = Depends(get_current_principal)):
    """Owner data export. Built from explicit field allowlists in
    app/bots/history.py, so provider keys / webhook secrets / internal ids
    are excluded by construction."""
    from fastapi.responses import Response

    from app.bots import history
    from app.bots.service import BotError

    if not principal.company_id:
        raise HTTPException(status_code=404, detail={"code": "no_company", "message": "No company found."})
    try:
        with connection() as conn:
            payload = history.company_export(conn, principal.company_id)
    except BotError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})
    return Response(
        content=history.export_json_bytes(payload),
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="company-export.json"'},
    )
