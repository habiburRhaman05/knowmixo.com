"""MFA API (D8.5): setup/confirm/disable for the authenticated owner,
login-time verification, and step-up tokens for destructive actions.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.service import SessionPrincipal, create_session
from app.db import connection
from app.deps import get_current_principal
from app.security import mfa
from app.security.mfa_login import consume_mfa_login_challenge, resolve_mfa_login_challenge

router = APIRouter(prefix="/api/v1/auth/mfa", tags=["mfa"])


def _raise(exc: mfa.MFAError):
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


class ConfirmRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


class LoginVerifyRequest(BaseModel):
    mfa_token: str
    code: str = Field(..., min_length=6, max_length=12)  # TOTP (6) or recovery code (longer)


class StepUpRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=12)


@router.post("/setup")
async def setup(principal: SessionPrincipal = Depends(get_current_principal)):
    try:
        with connection() as conn:
            return mfa.setup_totp(conn, principal.user_id, principal.email)
    except mfa.MFAError as exc:
        _raise(exc)


@router.post("/confirm")
async def confirm(body: ConfirmRequest, principal: SessionPrincipal = Depends(get_current_principal)):
    try:
        with connection() as conn:
            codes = mfa.confirm_totp(conn, principal.user_id, body.code)
    except mfa.MFAError as exc:
        _raise(exc)
    return {"enabled": True, "recovery_codes": codes}


@router.post("/disable")
async def disable(principal: SessionPrincipal = Depends(get_current_principal)):
    with connection() as conn:
        mfa.disable_mfa(conn, principal.user_id)
    return {"enabled": False}


@router.get("/status")
async def status(principal: SessionPrincipal = Depends(get_current_principal)):
    with connection() as conn:
        return {"enabled": mfa.is_mfa_enabled(conn, principal.user_id)}


@router.post("/login-verify")
async def login_verify(body: LoginVerifyRequest):
    """Completes a login that returned {"mfa_required": True} -- accepts
    either a 6-digit TOTP code or a recovery code."""
    user_id = resolve_mfa_login_challenge(body.mfa_token)
    if not user_id:
        raise HTTPException(401, detail={"code": "mfa_challenge_expired", "message": "This login attempt has expired. Log in again."})

    with connection() as conn:
        ok = mfa.verify_totp(conn, user_id, body.code) or mfa.verify_recovery_code(conn, user_id, body.code)
        if not ok:
            raise HTTPException(401, detail={"code": "invalid_mfa_code", "message": "Invalid authenticator or recovery code."})
        consume_mfa_login_challenge(body.mfa_token)
        session_token = create_session(conn, user_id)

    return {"session_token": session_token}


@router.post("/step-up")
async def step_up(body: StepUpRequest, principal: SessionPrincipal = Depends(get_current_principal)):
    """Issues a short-lived step-up token after re-proving MFA, for
    passing to a destructive-action endpoint via the X-Step-Up-Token
    header (see app.deps.require_step_up)."""
    with connection() as conn:
        if not mfa.is_mfa_enabled(conn, principal.user_id):
            raise HTTPException(400, detail={"code": "mfa_not_enabled", "message": "MFA is not enabled on this account."})
        ok = mfa.verify_totp(conn, principal.user_id, body.code) or mfa.verify_recovery_code(conn, principal.user_id, body.code)
        if not ok:
            raise HTTPException(401, detail={"code": "invalid_mfa_code", "message": "Invalid authenticator or recovery code."})
        token = mfa.issue_step_up_token(conn, principal.user_id)
    return {"step_up_token": token, "expires_in_seconds": mfa.STEP_UP_TTL_SECONDS}
