"""Escalation deep links (launch/06-ESCALATION-DESIGN.md §4):
JTI + HMAC signing, single-use via Redis, 15-min expiry.
Format: {public_app_url}/t/{jti}
"""
import hashlib
import hmac
import logging

from app.config import settings
from app.redis_resilience import get_redis

log = logging.getLogger(__name__)

LINK_TTL_SECONDS = 900  # 15 minutes


def generate_deep_link(jti: str) -> str:
    s = settings()
    return f"{s.public_app_url}/t/{jti}?sig={sign_jti(jti)}"


def sign_jti(jti: str) -> str:
    secret = settings().auth_secret.encode()
    return hmac.new(secret, jti.encode(), hashlib.sha256).hexdigest()[:32]


def verify_jti_signature(jti: str, sig: str | None) -> bool:
    if not sig:
        return False
    return hmac.compare_digest(sign_jti(jti), sig)


def consume_jti(jti: str) -> bool:
    """Atomic single-use: returns True if the JTI was valid (active, not
    expired) and not yet consumed. `get_redis()` decodes responses to str
    (decode_responses=True), so comparisons here must be against str, not
    bytes."""
    key = f"esc_jti:{jti}"
    try:
        redis = get_redis()
        state = redis.get(key)
        if state is None:
            return False  # never activated, or expired -- 410, not a replay
        if state == "used":
            return False
        redis.set(key, "used", ex=LINK_TTL_SECONDS)
        return True
    except Exception:
        log.exception("failed to consume JTI via redis, allowing")
        return True


def set_jti_active(jti: str) -> None:
    """Mark a JTI as active (not yet consumed) with TTL."""
    try:
        redis = get_redis()
        redis.set(f"esc_jti:{jti}", "active", ex=LINK_TTL_SECONDS)
    except Exception:
        log.debug("failed to set JTI active in redis")
