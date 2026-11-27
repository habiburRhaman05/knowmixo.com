"""Per-IP rate limiting dependency (docs/03-RISKS-AND-BLOCKERS.md §2.8:
"only visitor session bootstrap is rate-limited today; signup, login,
forgot/reset, Google token, verify-email, public chat, lead and feedback
are all unlimited and abusable").

Generalizes the bespoke per-IP limiter that already existed for visitor
session bootstrap (app/public/router.py) into one reusable dependency so
every other listed route gets the same protection without duplicating the
Redis call-and-degrade logic.
"""
from fastapi import HTTPException, Request

from app.redis_resilience import RateLimiter, get_redis


def _error(status: int, code: str, message: str, headers: dict | None = None) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message}, headers=headers)


def RateLimited(limit: int, window_seconds: int, key_prefix: str):
    """Returns a FastAPI dependency enforcing `limit` requests per
    `window_seconds` per client IP, scoped to `key_prefix` so different
    routes never share a bucket.

    Best-effort: a Redis outage (or the resilience wrapper's own degraded
    mode) fails OPEN -- a rate-limiter problem must never turn into a 500
    on a public or pre-auth path."""

    def _dependency(request: Request) -> None:
        try:
            ip = request.client.host if request.client else "unknown"
            allowed, _remaining = RateLimiter(get_redis(), key_prefix).check_limit(ip, limit, window_seconds)
        except Exception:  # noqa: BLE001
            return
        if not allowed:
            raise _error(
                429,
                "rate_limited",
                "Too many requests. Try again shortly.",
                headers={"Retry-After": str(window_seconds)},
            )

    return _dependency
