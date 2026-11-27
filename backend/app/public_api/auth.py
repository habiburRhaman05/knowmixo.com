"""Public API auth: Bearer km_live_... resolution + per-route scope
requirement (ADR 007). Rate limiting is keyed by the resolved API key
(not client IP, unlike app.security.rate_limit.RateLimited) -- per-key
is an explicit test requirement (launch/14-API-TEST-PLAN.md §2.11), and
IP-based limiting would let unrelated keys behind the same NAT share a
bucket, or let one key dodge its limit by rotating source IPs.
"""
from fastapi import Depends, Header

from app.public_api.keys import ApiKeyPrincipal, resolve_api_key
from app.public_api.problem_details import PublicAPIError
from app.redis_resilience import RateLimiter, get_redis

RATE_LIMIT_PER_MINUTE = 60  # not specified anywhere in launch/*.md; this session's own chosen number


def get_api_key_principal(authorization: str | None = Header(default=None)) -> ApiKeyPrincipal:
    if not authorization or not authorization.startswith("Bearer "):
        raise PublicAPIError(401, "unauthenticated", "Missing or malformed Authorization header.")
    token = authorization.removeprefix("Bearer ").strip()
    principal = resolve_api_key(token) if token else None
    if not principal:
        raise PublicAPIError(401, "invalid_api_key", "Invalid or revoked API key.")

    try:
        allowed, _remaining = RateLimiter(get_redis(), "public_api").check_limit(principal.key_id, RATE_LIMIT_PER_MINUTE, 60)
    except Exception:
        allowed = True  # fail open on a Redis outage, same policy as app.security.rate_limit.RateLimited
    if not allowed:
        raise PublicAPIError(429, "rate_limited", "Too many requests for this API key. Try again shortly.", retry_after_seconds=60)

    return principal


def require_scope(scope: str):
    def dependency(principal: ApiKeyPrincipal = Depends(get_api_key_principal)) -> ApiKeyPrincipal:
        if not principal.has_scope(scope):
            raise PublicAPIError(403, "insufficient_scope", f"This API key does not have the '{scope}' scope.")
        return principal

    return dependency
