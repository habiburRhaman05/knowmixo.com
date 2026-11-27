"""Entitlements: Redis-cached plan features + limits lookup
(launch/09-BILLING-PAYMENTS.md §5). Cache key `ent:{company_id}`,
TTL 60 s, falls back to DB on cache miss.
"""
import json
import logging

from app.db import connection
from app.redis_resilience import get_redis

log = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 60
_DEFAULT_PLAN_ID = "free"


def _db_read_entitlements(company_id: str) -> dict:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT p.id AS plan_id, p.limits, p.features, s.status
            FROM subscriptions s
            JOIN plans p ON p.id = s.plan_id
            WHERE s.company_id = %s AND s.status IN ('active', 'trialing')
            ORDER BY p.sort_order DESC LIMIT 1
            """,
            (company_id,),
        ).fetchone()
        if row:
            merged = {**(row["limits"] or {}), **(row["features"] or {})}
            merged["plan_id"] = row["plan_id"]
            merged["subscription_status"] = row["status"]
            return merged
        # Fall back to free plan
        free = conn.execute("SELECT limits, features FROM plans WHERE id = %s", (_DEFAULT_PLAN_ID,)).fetchone()
        if free:
            merged = {**(free["limits"] or {}), **(free["features"] or {})}
            merged["plan_id"] = _DEFAULT_PLAN_ID
            merged["subscription_status"] = "free"
            return merged
        return {"plan_id": _DEFAULT_PLAN_ID, "subscription_status": "free"}


def entitlements(company_id: str) -> dict:
    cache_key = f"ent:{company_id}"
    try:
        redis = get_redis()
        cached = redis.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        log.debug("entitlements cache miss (redis unavailable)")

    result = _db_read_entitlements(company_id)

    try:
        redis = get_redis()
        redis.set(cache_key, json.dumps(result), ex=CACHE_TTL_SECONDS)
    except Exception:
        log.debug("entitlements cache write failed")

    return result


def invalidate_entitlements(company_id: str) -> None:
    try:
        redis = get_redis()
        redis.delete(f"ent:{company_id}")
    except Exception:
        pass


def require_feature(company_id: str, feature: str) -> None:
    ent = entitlements(company_id)
    if not ent.get(feature):
        from fastapi import HTTPException
        raise HTTPException(
            status_code=403,
            detail={"code": "feature_not_available", "message": f"Your plan does not include {feature}."},
        )


def require_quota(company_id: str, resource: str, n: int = 1) -> None:
    ent = entitlements(company_id)
    limit = ent.get(resource)
    if limit is None:
        return  # unlimited
    with connection() as conn:
        if resource == "ai_replies_per_month":
            row = conn.execute(
                """
                SELECT COALESCE(SUM(quantity), 0) AS used
                FROM usage_events
                WHERE company_id = %s AND kind = 'ai_reply'
                  AND created_at >= date_trunc('month', now())
                """,
                (company_id,),
            ).fetchone()
            used = int(row["used"]) if row else 0
            if used + n > int(limit):
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=429,
                    detail={"code": "quota_exhausted", "message": f"Monthly {resource} limit reached."},
                    headers={"Retry-After": "3600"},
                )
