"""Alerts: 3 built-in rules (D8.3, launch/12-FEASIBILITY-MATRIX.md:119
"quota 80/100, unanswered spike, ingestion failure"). Delivered by email
to the company owner -- no exact thresholds/delivery mechanics are
specified anywhere, so the numbers and "owner email" delivery channel
below are this session's from-scratch design.

Debounced via alert_state so a sustained condition (quota pinned at
100%, a source still failing) sends one alert per rule per cooldown
window, not one per evaluation tick.
"""
import json
import logging
from datetime import datetime, timedelta, timezone

from app.chat import quota
from app.db import connection
from app.email import send_email

log = logging.getLogger(__name__)

UNANSWERED_SPIKE_THRESHOLD = 5  # answer_no_evidence events
UNANSWERED_SPIKE_WINDOW_MINUTES = 60
ALERT_COOLDOWN_MINUTES = 60  # don't re-fire the same rule more often than this


def _should_fire(conn, company_id: str, rule: str, value: dict) -> bool:
    row = conn.execute(
        "SELECT last_triggered_at FROM alert_state WHERE company_id = %s AND rule = %s",
        (company_id, rule),
    ).fetchone()
    if row and row["last_triggered_at"]:
        elapsed = (datetime.now(timezone.utc) - row["last_triggered_at"]).total_seconds()
        if elapsed < ALERT_COOLDOWN_MINUTES * 60:
            return False
    conn.execute(
        """
        INSERT INTO alert_state (company_id, rule, last_triggered_at, last_value)
        VALUES (%s, %s, now(), %s::jsonb)
        ON CONFLICT (company_id, rule) DO UPDATE SET last_triggered_at = now(), last_value = EXCLUDED.last_value
        """,
        (company_id, rule, json.dumps(value)),
    )
    return True


def _owner_email(conn, company_id: str) -> str | None:
    row = conn.execute(
        "SELECT u.email FROM users u JOIN companies c ON c.owner_user_id = u.id WHERE c.id = %s",
        (company_id,),
    ).fetchone()
    return row["email"] if row else None


def _notify(conn, company_id: str, subject: str, body: str) -> None:
    email = _owner_email(conn, company_id)
    if email:
        try:
            send_email(email, subject, body)
        except Exception:
            log.exception("failed to send alert email to %s", email)
    else:
        log.warning("no owner email found for company %s, skipping email alert", company_id)

    try:
        from app.integrations.slack import post_alert
        post_alert(company_id, f"*{subject}*\n{body}")
    except Exception:
        log.exception("failed to post Slack alert for company %s", company_id)


def check_quota_threshold(conn, company_id: str) -> None:
    snap = quota.usage_snapshot(conn, company_id)
    daily = snap["company_daily"]
    limit = daily["limit"]
    if not limit:
        return
    ratio = daily["requests"] / limit
    if ratio >= 1.0:
        level = "100%"
    elif ratio >= 0.8:
        level = "80%"
    else:
        return
    if _should_fire(conn, company_id, f"quota_{level}", {"requests": daily["requests"], "limit": limit}):
        _notify(
            conn, company_id,
            f"Knowmivo: daily AI reply quota at {level}",
            f"Your assistant has used {daily['requests']} of {limit} daily AI replies ({level}). "
            f"Consider upgrading your plan to avoid interruptions.",
        )


def check_unanswered_spike(conn, company_id: str) -> None:
    since = datetime.now(timezone.utc) - timedelta(minutes=UNANSWERED_SPIKE_WINDOW_MINUTES)
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM analytics_events WHERE company_id = %s AND event_type = 'answer_no_evidence' AND created_at >= %s",
        (company_id, since),
    ).fetchone()
    count = int(row["n"]) if row else 0
    if count < UNANSWERED_SPIKE_THRESHOLD:
        return
    if _should_fire(conn, company_id, "unanswered_spike", {"count": count, "window_minutes": UNANSWERED_SPIKE_WINDOW_MINUTES}):
        _notify(
            conn, company_id,
            "Knowmivo: spike in unanswered questions",
            f"Your assistant couldn't find an answer for {count} questions in the last "
            f"{UNANSWERED_SPIKE_WINDOW_MINUTES} minutes. Check the Gaps queue to add missing answers.",
        )


def check_ingestion_failures(conn, company_id: str) -> None:
    since = datetime.now(timezone.utc) - timedelta(minutes=UNANSWERED_SPIKE_WINDOW_MINUTES)
    rows = conn.execute(
        """
        SELECT d.title FROM document_versions dv
        JOIN documents d ON d.id = dv.document_id
        WHERE d.company_id = %s AND dv.status = 'failed' AND dv.created_at >= %s
        """,
        (company_id, since),
    ).fetchall()
    if not rows:
        return
    titles = ", ".join(r["title"] for r in rows[:5])
    if _should_fire(conn, company_id, "ingestion_failure", {"count": len(rows)}):
        _notify(
            conn, company_id,
            "Knowmivo: a knowledge source failed to process",
            f"{len(rows)} source(s) failed to ingest recently: {titles}. Check your Knowledge sources page.",
        )


def evaluate_all_companies() -> int:
    """Runs all 3 rules for every company with at least one bot. Called
    by the job runner (kind='evaluate_alerts'), not inline in any
    request path."""
    checked = 0
    with connection() as conn:
        companies = conn.execute("SELECT DISTINCT company_id FROM bots").fetchall()
        for row in companies:
            company_id = str(row["company_id"])
            try:
                check_quota_threshold(conn, company_id)
                check_unanswered_spike(conn, company_id)
                check_ingestion_failures(conn, company_id)
                checked += 1
            except Exception:
                log.exception("alert evaluation failed for company %s", company_id)
    return checked
