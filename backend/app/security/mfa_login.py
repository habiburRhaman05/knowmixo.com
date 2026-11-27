"""Ephemeral login-time MFA challenge (D8.5): bridges password/Google
auth succeeding to a TOTP/recovery-code check before a real session is
issued. Redis-backed (not a table) since it's a 5-minute, purely
transient hand-off with no durability requirement beyond that window --
same pattern as app.escalation.verification's opt-in codes.
"""
import logging

from app.redis_resilience import get_redis
from app.security.tokens import generate_opaque_token, hash_token

log = logging.getLogger(__name__)

CHALLENGE_TTL_SECONDS = 5 * 60


def _key(token_hash: str) -> str:
    return f"mfa_login:{token_hash}"


def issue_mfa_login_challenge(user_id: str) -> str:
    token = generate_opaque_token()
    get_redis().setex(_key(hash_token(token)), CHALLENGE_TTL_SECONDS, user_id)
    return token


def resolve_mfa_login_challenge(token: str) -> str | None:
    """Does NOT consume -- a wrong code should let the user retry within
    the same 5-minute window rather than burning the challenge on one
    mistaken attempt. Call consume_mfa_login_challenge after a successful
    verify to prevent reuse of the same challenge for a second session."""
    return get_redis().get(_key(hash_token(token)))


def consume_mfa_login_challenge(token: str) -> None:
    get_redis().delete(_key(hash_token(token)))
