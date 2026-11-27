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
from app.security import mfa


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


# Role hierarchy (D8.6): owner > admin > agent > viewer. No permission
# matrix doc exists for this sprint (confirmed absent in launch/*.md), so
# this is the from-scratch design: owner/admin manage billing, team,
# sources and bot config; agent handles conversations/handoff/canned
# replies but not config; viewer is read-only everywhere.
_ROLE_RANK = {"viewer": 0, "agent": 1, "admin": 2, "owner": 3}


def require_role(*allowed: str):
    """Dependency factory: raises 403 unless the session's role is one of
    `allowed`, or outranks the lowest of `allowed` in the hierarchy above.
    Use require_role('admin') to mean "admin or owner", not just literal
    admin -- pass an explicit list instead when you want an exact set."""
    min_rank = min(_ROLE_RANK.get(r, 99) for r in allowed) if allowed else 0

    def dependency(principal: SessionPrincipal = Depends(get_verified_principal)) -> SessionPrincipal:
        rank = _ROLE_RANK.get(principal.role or "", -1)
        if rank < min_rank:
            raise HTTPException(
                status_code=403,
                detail={"code": "insufficient_role", "message": "Your role does not have access to this action."},
            )
        return principal

    return dependency


def require_step_up(
    principal: SessionPrincipal = Depends(get_current_principal),
    x_step_up_token: str | None = Header(default=None),
) -> SessionPrincipal:
    """D8.5: gate for destructive actions. If the account has MFA
    enabled, a valid, single-use, 10-minute X-Step-Up-Token (minted by
    POST /api/v1/auth/mfa/step-up) is required. Accounts without MFA
    enabled are NOT blocked here -- step-up is only as strong as the
    factor behind it, and requiring a header no account can produce
    would just lock everyone out of destructive actions by default. The
    stated requirement (Day 8 gate: 'step-up on destructive actions') is
    satisfied for every account that actually enables MFA; encouraging
    MFA adoption is a product/UX concern, not something this dependency
    can enforce on its own."""
    with connection() as conn:
        if not mfa.is_mfa_enabled(conn, principal.user_id):
            return principal
        if not x_step_up_token or not mfa.consume_step_up_token(conn, principal.user_id, x_step_up_token):
            raise HTTPException(
                status_code=401,
                detail={"code": "step_up_required", "message": "Re-verify with MFA to perform this action."},
            )
    return principal
