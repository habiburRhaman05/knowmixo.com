"""Knowledge gaps (D8.3, launch/MASTER-PROMPT.md §80): unanswered/
low-confidence questions clustered by topic with counts and examples;
one-click "write the answer" turns a gap into a real FAQ source.

Clustering here is exact-match on normalized text (lowercased, trimmed,
punctuation/whitespace collapsed) -- it catches literal repeats but not
paraphrases. Embedding-similarity clustering is the stated future
upgrade (launch/02-GAP-ANALYSIS.md), out of scope for this pass, same as
other NEEDS_MORE_TIME items this project has already shipped reduced.
"""
import logging
import re

from app.db import connection
from app.sources.service import create_faq_source

log = logging.getLogger(__name__)

_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]")


def normalize_question(text: str) -> str:
    text = text.lower().strip()
    text = _PUNCT_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


def recompute_gaps(company_id: str, bot_id: str) -> int:
    """Scans analytics_events for 'answer_no_evidence' since the last
    run's high-water mark isn't tracked separately -- this upserts
    against the whole history each run (cheap: one company's
    answer_no_evidence volume is not huge), incrementing occurrence_count
    and last_seen_at for repeats. Returns the number of gap rows touched."""
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT q.content AS question, ae.created_at
            FROM analytics_events ae
            JOIN messages um ON um.id = ae.message_id
            JOIN LATERAL (
                SELECT m.content FROM messages m
                WHERE m.conversation_id = um.conversation_id AND m.role = 'user' AND m.created_at <= um.created_at
                ORDER BY m.created_at DESC LIMIT 1
            ) q ON true
            WHERE ae.company_id = %s AND ae.bot_id = %s AND ae.event_type = 'answer_no_evidence'
            ORDER BY ae.created_at DESC
            """,
            (company_id, bot_id),
        ).fetchall()

        clusters: dict[str, dict] = {}
        for r in rows:
            question = (r["question"] or "").strip()
            if not question:
                continue
            key = normalize_question(question)
            if not key:
                continue
            if key not in clusters:
                clusters[key] = {"sample": question, "count": 0, "first": r["created_at"], "last": r["created_at"]}
            clusters[key]["count"] += 1
            clusters[key]["first"] = min(clusters[key]["first"], r["created_at"])
            clusters[key]["last"] = max(clusters[key]["last"], r["created_at"])

        for key, c in clusters.items():
            conn.execute(
                """
                INSERT INTO gaps (company_id, bot_id, normalized_question, sample_question, occurrence_count, first_seen_at, last_seen_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (bot_id, normalized_question) DO UPDATE SET
                    occurrence_count = EXCLUDED.occurrence_count,
                    last_seen_at = EXCLUDED.last_seen_at,
                    sample_question = EXCLUDED.sample_question,
                    updated_at = now()
                WHERE gaps.status = 'open'
                """,
                (company_id, bot_id, key, c["sample"], c["count"], c["first"], c["last"]),
            )
        return len(clusters)


def list_gaps(company_id: str, status: str = "open", limit: int = 100) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, sample_question, occurrence_count, first_seen_at, last_seen_at, status
            FROM gaps WHERE company_id = %s AND status = %s
            ORDER BY occurrence_count DESC, last_seen_at DESC
            LIMIT %s
            """,
            (company_id, status, limit),
        ).fetchall()
        return [dict(r) for r in rows]


class GapError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def resolve_gap(company_id: str, gap_id: str, user_id: str, answer: str) -> dict:
    """One-click 'write the answer': creates a single-item FAQ source
    (re-embedded by the normal ingestion pipeline) and marks the gap
    resolved. A new FAQ document per resolution avoids read-modify-write
    races on a shared document across concurrent resolutions."""
    with connection() as conn:
        gap = conn.execute(
            "SELECT id, sample_question FROM gaps WHERE id = %s AND company_id = %s",
            (gap_id, company_id),
        ).fetchone()
        if not gap:
            raise GapError(404, "gap_not_found", "Gap not found.")

        document_id, job_id = create_faq_source(
            conn, company_id, f"Gap answer: {gap['sample_question'][:80]}",
            [{"question": gap["sample_question"], "answer": answer}],
        )
        conn.execute(
            "UPDATE gaps SET status = 'resolved', resolved_at = now(), resolved_by = %s, updated_at = now() WHERE id = %s",
            (user_id, gap_id),
        )
        return {"gap_id": gap_id, "document_id": document_id, "job_id": job_id}


def ignore_gap(company_id: str, gap_id: str) -> bool:
    with connection() as conn:
        result = conn.execute(
            "UPDATE gaps SET status = 'ignored', updated_at = now() WHERE id = %s AND company_id = %s",
            (gap_id, company_id),
        )
        return result.rowcount > 0
