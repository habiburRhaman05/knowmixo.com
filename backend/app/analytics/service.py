"""Analytics: 3 core charts (D8.2, launch/13-SPRINT-10-DAYS.md,
launch/12-FEASIBILITY-MATRIX.md). Only TTFT has a precise spec
definition (launch/05-RAG-V2-SPEC.md: "time to first `delta` SSE event",
instrumented in both app.chat.pipeline.stream_turn and
app.chat.rag_v2.pipeline.stream_turn_v2 into messages.usage->>'ttft_ms').
"Conversations" and "deflection" have no formula anywhere in launch/*.md
(confirmed absent by search) -- these definitions are this session's
from-scratch design:
  - conversations: count of non-preview conversations CREATED per day.
  - deflection rate: of conversations created that day, the fraction
    that were NEVER handed off to a human (handed_off_at IS NULL) --
    i.e. the bot fully resolved them without escalation.
"""
from datetime import datetime, timedelta, timezone


def conversations_series(conn, company_id: str, date_from: datetime, date_to: datetime) -> list[dict]:
    rows = conn.execute(
        """
        SELECT date_trunc('day', c.created_at AT TIME ZONE 'UTC')::date AS day, COUNT(*) AS n
        FROM conversations c JOIN bots b ON b.id = c.bot_id
        WHERE b.company_id = %s AND NOT c.is_preview
          AND c.created_at >= %s AND c.created_at <= %s
        GROUP BY 1 ORDER BY 1
        """,
        (company_id, date_from, date_to),
    ).fetchall()
    return [{"day": r["day"].isoformat(), "count": int(r["n"])} for r in rows]


def deflection_series(conn, company_id: str, date_from: datetime, date_to: datetime) -> list[dict]:
    rows = conn.execute(
        """
        SELECT date_trunc('day', c.created_at AT TIME ZONE 'UTC')::date AS day,
               COUNT(*) AS total,
               COUNT(*) FILTER (WHERE c.handed_off_at IS NULL) AS deflected
        FROM conversations c JOIN bots b ON b.id = c.bot_id
        WHERE b.company_id = %s AND NOT c.is_preview
          AND c.created_at >= %s AND c.created_at <= %s
        GROUP BY 1 ORDER BY 1
        """,
        (company_id, date_from, date_to),
    ).fetchall()
    return [
        {
            "day": r["day"].isoformat(),
            "total": int(r["total"]),
            "deflected": int(r["deflected"]),
            "deflection_rate": round(int(r["deflected"]) / int(r["total"]), 4) if r["total"] else None,
        }
        for r in rows
    ]


def ttft_series(conn, company_id: str, date_from: datetime, date_to: datetime) -> list[dict]:
    rows = conn.execute(
        """
        SELECT date_trunc('day', m.created_at AT TIME ZONE 'UTC')::date AS day,
               percentile_cont(0.5) WITHIN GROUP (ORDER BY (m.usage->>'ttft_ms')::int) AS p50,
               percentile_cont(0.95) WITHIN GROUP (ORDER BY (m.usage->>'ttft_ms')::int) AS p95,
               COUNT(*) AS n
        FROM messages m
        JOIN conversations c ON c.id = m.conversation_id
        JOIN bots b ON b.id = c.bot_id
        WHERE b.company_id = %s AND NOT c.is_preview
          AND m.role = 'assistant' AND m.status = 'completed'
          AND m.usage->>'ttft_ms' IS NOT NULL
          AND m.created_at >= %s AND m.created_at <= %s
        GROUP BY 1 ORDER BY 1
        """,
        (company_id, date_from, date_to),
    ).fetchall()
    return [
        {
            "day": r["day"].isoformat(),
            "p50_ms": round(float(r["p50"])) if r["p50"] is not None else None,
            "p95_ms": round(float(r["p95"])) if r["p95"] is not None else None,
            "sample_count": int(r["n"]),
        }
        for r in rows
    ]


_METRICS = {
    "conversations": conversations_series,
    "deflection": deflection_series,
    "ttft": ttft_series,
}


def get_series(conn, company_id: str, metric: str, date_from: datetime | None, date_to: datetime | None) -> list[dict]:
    if metric not in _METRICS:
        raise ValueError(f"unknown metric: {metric}")
    to = date_to or datetime.now(timezone.utc)
    frm = date_from or (to - timedelta(days=30))
    return _METRICS[metric](conn, company_id, frm, to)
