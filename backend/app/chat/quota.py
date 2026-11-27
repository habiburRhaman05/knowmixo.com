"""Quota guard (docs/19 Phase 6 exit condition: "quota guard provably
blocking paid fallback under simulated exhaustion").

Reserve-before-call: a pending usage_reservations row is inserted under a
lock BEFORE any provider call, so concurrent requests cannot jointly
oversubscribe the daily budget. On success the reservation is committed
and usage_daily incremented; on any failure it is released.

Plan-aware monthly enforcement (J.5/J.6 launch punch-list item) layers on
top of this, additively: the flat daily company/global caps above stay
exactly as they were (free-tier abuse protection, plan-agnostic), and
`reserve()`/`commit()` now ALSO check/record against the owner's actual
plan limit (`plans.limits.ai_replies_per_month`) via `usage_events` --
whichever cap is stricter wins. This was a real, confirmed gap: the
`usage_events` table and `require_quota()` helper existed with zero
callers and zero writers until this change.
"""
from datetime import datetime, timedelta, timezone

from app.config import settings

RESERVATION_TTL_SECONDS = 180
_TODAY = "(now() AT TIME ZONE 'utc')::date"
_MONTH_START = "date_trunc('month', now())"


class QuotaExceeded(Exception):
    def __init__(self, scope: str, retry_after_seconds: int):
        super().__init__(scope)
        self.scope = scope  # 'company' | 'global'
        self.retry_after_seconds = retry_after_seconds


def next_reset_at() -> datetime:
    now = datetime.now(timezone.utc)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


def _seconds_until_reset() -> int:
    return max(1, int((next_reset_at() - datetime.now(timezone.utc)).total_seconds()))


def _next_month_start(now: datetime) -> datetime:
    if now.month == 12:
        return now.replace(year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    return now.replace(month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)


def _seconds_until_next_month() -> int:
    now = datetime.now(timezone.utc)
    return max(1, int((_next_month_start(now) - now).total_seconds()))


def _check_plan_monthly_quota(conn, company_id: str) -> None:
    """Raises QuotaExceeded("plan_monthly", ...) if the owner's plan's
    `ai_replies_per_month` limit (None = unlimited) is already used up
    this calendar month, per `usage_events(kind='ai_reply')`."""
    from app.billing.entitlements import entitlements

    limit = entitlements(company_id).get("ai_replies_per_month")
    if limit is None:
        return
    used = conn.execute(
        f"""
        SELECT COALESCE(SUM(quantity), 0) AS used FROM usage_events
        WHERE company_id = %s AND kind = 'ai_reply' AND created_at >= {_MONTH_START}
        """,
        (company_id,),
    ).fetchone()["used"]
    if int(used) >= int(limit):
        raise QuotaExceeded("plan_monthly", _seconds_until_next_month())


def _record_plan_monthly_usage(conn, company_id: str, conversation_id: str | None) -> None:
    conn.execute(
        "INSERT INTO usage_events (company_id, conversation_id, kind, quantity) VALUES (%s, %s, 'ai_reply', 1)",
        (company_id, conversation_id),
    )


def _ensure_row(conn, company_id: str) -> None:
    conn.execute(
        f"INSERT INTO usage_daily (company_id, date) VALUES (%s, {_TODAY}) ON CONFLICT (company_id, date) DO NOTHING",
        (company_id,),
    )


def usage_snapshot(conn, company_id: str) -> dict:
    """Used + in-flight request counts for today (UTC), company and global."""
    s = settings()
    company = conn.execute(
        f"""
        SELECT COALESCE(SUM(chat_requests_count), 0) AS used, COALESCE(SUM(chat_tokens_count), 0) AS tokens,
               COALESCE(SUM(embeddings_count), 0) AS embeddings
        FROM usage_daily WHERE company_id = %s AND date = {_TODAY}
        """,
        (company_id,),
    ).fetchone()
    pending_company = conn.execute(
        "SELECT COUNT(*) AS n FROM usage_reservations WHERE company_id = %s AND status = 'pending' AND expires_at > now()",
        (company_id,),
    ).fetchone()["n"]
    global_used = conn.execute(
        f"SELECT COALESCE(SUM(chat_requests_count), 0) AS used FROM usage_daily WHERE date = {_TODAY}"
    ).fetchone()["used"]
    pending_global = conn.execute(
        "SELECT COUNT(*) AS n FROM usage_reservations WHERE status = 'pending' AND expires_at > now()"
    ).fetchone()["n"]
    company_total = int(company["used"]) + int(pending_company)
    global_total = int(global_used) + int(pending_global)
    exhausted = company_total >= s.company_chat_daily_limit or global_total >= s.global_chat_daily_limit
    return {
        "company_daily": {
            "requests": int(company["used"]),
            "tokens": int(company["tokens"]),
            "embeddings": int(company["embeddings"]),
            "limit": s.company_chat_daily_limit,
        },
        "global_daily": {"requests": int(global_used), "limit": s.global_chat_daily_limit},
        "quota_state": "exhausted" if exhausted else "ok",
        "next_reset_at": next_reset_at().isoformat(),
        "_company_total": company_total,
        "_global_total": global_total,
    }


def public_usage(snapshot: dict) -> dict:
    return {k: v for k, v in snapshot.items() if not k.startswith("_")}


def reserve(conn, company_id: str, conversation_id: str | None, estimated_tokens: int) -> str:
    """Returns the reservation id or raises QuotaExceeded. Must run inside
    the caller's transaction; the advisory lock serialises check+insert."""
    s = settings()
    _ensure_row(conn, company_id)
    conn.execute("SELECT pg_advisory_xact_lock(hashtext('knowmivo_chat_quota'))")
    snap = usage_snapshot(conn, company_id)
    if snap["_company_total"] >= s.company_chat_daily_limit:
        raise QuotaExceeded("company", _seconds_until_reset())
    if snap["_global_total"] >= s.global_chat_daily_limit:
        raise QuotaExceeded("global", _seconds_until_reset())
    _check_plan_monthly_quota(conn, company_id)
    row = conn.execute(
        """
        INSERT INTO usage_reservations (company_id, conversation_id, estimated_tokens, expires_at)
        VALUES (%s, %s, %s, now() + make_interval(secs => %s)) RETURNING id
        """,
        (company_id, conversation_id, estimated_tokens, RESERVATION_TTL_SECONDS),
    ).fetchone()
    return str(row["id"])


def commit(conn, company_id: str, reservation_id: str, tokens_used: int, conversation_id: str | None = None) -> None:
    conn.execute("UPDATE usage_reservations SET status = 'committed' WHERE id = %s", (reservation_id,))
    _ensure_row(conn, company_id)
    conn.execute(
        f"""
        UPDATE usage_daily SET chat_requests_count = chat_requests_count + 1,
            chat_tokens_count = chat_tokens_count + %s, updated_at = now()
        WHERE company_id = %s AND date = {_TODAY}
        """,
        (tokens_used, company_id),
    )
    _record_plan_monthly_usage(conn, company_id, conversation_id)


def release(conn, reservation_id: str) -> None:
    conn.execute(
        "UPDATE usage_reservations SET status = 'released' WHERE id = %s AND status = 'pending'",
        (reservation_id,),
    )


def record_embedding(conn, company_id: str, count: int = 1) -> None:
    _ensure_row(conn, company_id)
    conn.execute(
        f"UPDATE usage_daily SET embeddings_count = embeddings_count + %s, updated_at = now() WHERE company_id = %s AND date = {_TODAY}",
        (count, company_id),
    )
