"""Quota guard (docs/19 Phase 6 exit condition: "quota guard provably
blocking paid fallback under simulated exhaustion").

Reserve-before-call: a pending usage_reservations row is inserted under a
lock BEFORE any provider call, so concurrent requests cannot jointly
oversubscribe the daily budget. On success the reservation is committed
and usage_daily incremented; on any failure it is released.
"""
from datetime import datetime, timedelta, timezone

from app.config import settings

RESERVATION_TTL_SECONDS = 180
_TODAY = "(now() AT TIME ZONE 'utc')::date"


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
    row = conn.execute(
        """
        INSERT INTO usage_reservations (company_id, conversation_id, estimated_tokens, expires_at)
        VALUES (%s, %s, %s, now() + make_interval(secs => %s)) RETURNING id
        """,
        (company_id, conversation_id, estimated_tokens, RESERVATION_TTL_SECONDS),
    ).fetchone()
    return str(row["id"])


def commit(conn, company_id: str, reservation_id: str, tokens_used: int) -> None:
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
