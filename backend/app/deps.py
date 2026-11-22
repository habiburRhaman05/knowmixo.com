"""Real session/principal resolution, replacing app/demo_context.py.

Every protected route depends on get_current_principal (or
get_verified_principal). There is no code path here that defaults to an
authorized principal -- missing, malformed, expired or revoked credentials
all fail closed with 401, and company scope is derived from the resolved
session's own membership, never trusted from a client-supplied body/query
value (docs/11-AGENT-RULES.md rule 2).
"""
from fastapi import Depends, Header, HTTPException

from app.auth.service import SessionPrincipal, resolve_session
from app.db import connection


def get_current_principal(authorization: str | None = Header(default=None)) -> SessionPrincipal:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"code": "unauthenticated", "message": "Missing or malformed session."})

    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail={"code": "unauthenticated", "message": "Missing or malformed session."})

    with connection() as conn:
        principal = resolve_session(conn, token)

    if principal is None:
        raise HTTPException(status_code=401, detail={"code": "unauthenticated", "message": "Session is invalid or expired."})

    return principal


def get_verified_principal(principal: SessionPrincipal = Depends(get_current_principal)) -> SessionPrincipal:
    """Use on routes the PRD marks owner-only-after-verification (publish,
    owner chat preview, etc.) -- per 02-ACCEPTANCE.md: 'Unverified password
    accounts cannot publish or chat as owner.'"""
    if not principal.email_verified:
        raise HTTPException(
            status_code=403,
            detail={"code": "email_not_verified", "message": "Verify your email to use this feature."},
        )
    return principal
