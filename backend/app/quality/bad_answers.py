"""Bad-answers queue (D8.3, launch/MASTER-PROMPT.md §81): flagged via
thumbs-down, low confidence (rag_traces.grade sufficiency or rerank
score), a verifier hallucination flag, or an escalation off that
message's conversation. Shown with trace; owner can correct it, and the
correction becomes knowledge (a new FAQ source, same mechanism as gap
resolution).
"""
import logging

from app.db import connection
from app.sources.service import create_faq_source

log = logging.getLogger(__name__)


class BadAnswerError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def list_queue(company_id: str, limit: int = 100) -> list[dict]:
    """Union of candidate bad answers not yet reviewed (no row in
    bad_answer_reviews, or an 'open' row) -- thumbs-down, verifier
    unfaithful, or the conversation got escalated off the back of this
    message's turn."""
    with connection() as conn:
        rows = conn.execute(
            """
            WITH candidates AS (
                SELECT m.id AS message_id, m.conversation_id, m.content, m.created_at, 'thumbs_down' AS reason
                FROM messages m
                JOIN feedback f ON f.message_id = m.id AND f.rating = -1
                WHERE m.role = 'assistant'

                UNION

                SELECT m.id, m.conversation_id, m.content, m.created_at, 'hallucination'
                FROM messages m
                JOIN rag_traces rt ON rt.message_id = m.id
                WHERE m.role = 'assistant' AND rt.verifier_result->>'faithful' = 'false'

                UNION

                SELECT m.id, m.conversation_id, m.content, m.created_at, 'escalated'
                FROM messages m
                JOIN rag_traces rt ON rt.message_id = m.id
                WHERE m.role = 'assistant' AND rt.escalated = true
            )
            SELECT c.message_id, c.conversation_id, c.content, c.created_at,
                   array_agg(DISTINCT c.reason) AS reasons,
                   COALESCE(r.status, 'open') AS status
            FROM candidates c
            JOIN conversations conv ON conv.id = c.conversation_id
            JOIN bots b ON b.id = conv.bot_id
            LEFT JOIN bad_answer_reviews r ON r.message_id = c.message_id
            WHERE b.company_id = %s AND (r.status IS NULL OR r.status = 'open')
            GROUP BY c.message_id, c.conversation_id, c.content, c.created_at, r.status
            ORDER BY c.created_at DESC
            LIMIT %s
            """,
            (company_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_detail(company_id: str, message_id: str) -> dict | None:
    with connection() as conn:
        msg = conn.execute(
            """
            SELECT m.id, m.conversation_id, m.content, m.citations, m.created_at
            FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            JOIN bots b ON b.id = c.bot_id
            WHERE m.id = %s AND b.company_id = %s
            """,
            (message_id, company_id),
        ).fetchone()
        if not msg:
            return None
        trace = conn.execute(
            """
            SELECT intent, severity, rewritten_queries, retrieved, reranked, grade_iterations,
                   verifier_result, abstained, escalated
            FROM rag_traces WHERE message_id = %s
            """,
            (message_id,),
        ).fetchone()
        review = conn.execute(
            "SELECT status, correction_text, corrected_at FROM bad_answer_reviews WHERE message_id = %s",
            (message_id,),
        ).fetchone()
        return {
            "message": dict(msg),
            "trace": dict(trace) if trace else None,
            "review": dict(review) if review else None,
        }


def correct_answer(company_id: str, message_id: str, user_id: str, correction_text: str, question_hint: str | None = None) -> dict:
    with connection() as conn:
        msg = conn.execute(
            """
            SELECT m.id, m.conversation_id FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            JOIN bots b ON b.id = c.bot_id
            WHERE m.id = %s AND b.company_id = %s
            """,
            (message_id, company_id),
        ).fetchone()
        if not msg:
            raise BadAnswerError(404, "message_not_found", "Message not found.")

        question = question_hint
        if not question:
            prior = conn.execute(
                """
                SELECT content FROM messages
                WHERE conversation_id = %s AND role = 'user' AND created_at <= (SELECT created_at FROM messages WHERE id = %s)
                ORDER BY created_at DESC LIMIT 1
                """,
                (msg["conversation_id"], message_id),
            ).fetchone()
            question = prior["content"] if prior else "Correction"

        document_id, job_id = create_faq_source(
            conn, company_id, f"Correction: {question[:80]}",
            [{"question": question, "answer": correction_text}],
        )

        conn.execute(
            """
            INSERT INTO bad_answer_reviews (company_id, message_id, conversation_id, reason, status, correction_text, corrected_by, corrected_at)
            VALUES (%s, %s, %s, 'correction', 'corrected', %s, %s, now())
            ON CONFLICT (message_id) DO UPDATE SET
                status = 'corrected', correction_text = EXCLUDED.correction_text,
                corrected_by = EXCLUDED.corrected_by, corrected_at = now(), updated_at = now()
            """,
            (company_id, message_id, msg["conversation_id"], correction_text, user_id),
        )
        return {"message_id": message_id, "document_id": document_id, "job_id": job_id}


def dismiss(company_id: str, message_id: str) -> None:
    with connection() as conn:
        msg = conn.execute(
            """
            SELECT m.conversation_id FROM messages m
            JOIN conversations c ON c.id = m.conversation_id
            JOIN bots b ON b.id = c.bot_id
            WHERE m.id = %s AND b.company_id = %s
            """,
            (message_id, company_id),
        ).fetchone()
        if not msg:
            raise BadAnswerError(404, "message_not_found", "Message not found.")
        conn.execute(
            """
            INSERT INTO bad_answer_reviews (company_id, message_id, conversation_id, reason, status)
            VALUES (%s, %s, %s, 'dismissed', 'dismissed')
            ON CONFLICT (message_id) DO UPDATE SET status = 'dismissed', updated_at = now()
            """,
            (company_id, message_id, msg["conversation_id"]),
        )
