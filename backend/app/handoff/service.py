"""Handoff service (D5.5): conversation status management, assignment, canned replies."""
import json
import logging

from app.db import connection
from app.events.outbox import emit_event
from app.realtime.pubsub import conversation_channel, inbox_channel, publish_sync

log = logging.getLogger(__name__)

VALID_STATUSES = {"bot", "queued", "assigned", "resolved"}


def _notify(conn, company_id: str, conversation_id: str, topic: str, extra_payload: dict | None = None) -> None:
    """Fires the same realtime pattern as chat turns (ADR 005): durable
    event_outbox seed + live pub/sub fanout to both the owner inbox and
    the visitor's conversation state stream."""
    payload = {"conversation_id": conversation_id, **(extra_payload or {})}
    try:
        emit_event(conn, company_id, topic, payload)
    except Exception:
        log.warning("failed to emit %s outbox event", topic, exc_info=True)
    publish_sync(inbox_channel(company_id), topic, payload)
    publish_sync(conversation_channel(conversation_id), topic, payload)


class HandoffError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def send_agent_reply(company_id: str, conversation_id: str, text: str, actor_user_id: str | None = None) -> dict:
    """A human (or integration, via the public API's conversations:write
    scope) replying directly in a conversation -- bypasses the AI
    pipeline entirely, same role/shape as a normal assistant message so
    existing history/export code needs no special case. Pushed live to
    any open visitor tab via the conversation_channel sidecar stream
    (ADR 005) since this reply did not come from the usual per-turn SSE
    that the visitor's own message POST opens."""
    with connection() as conn:
        conv = conn.execute(
            """
            SELECT c.id FROM conversations c JOIN bots b ON b.id = c.bot_id
            WHERE c.id = %s AND b.company_id = %s
            """,
            (conversation_id, company_id),
        ).fetchone()
        if not conv:
            raise HandoffError(404, "conversation_not_found", "Conversation not found.")

        # D9.6 security suite: this text is authored by a human agent OR
        # (via the public API's conversations:write scope) a third-party
        # integration holding a company API key -- sanitise before it can
        # ever reach a visitor's widget, same as LLM-generated answers.
        from app.chat.rag_v2.stages.postprocess import sanitize_html
        text = sanitize_html(text)

        row = conn.execute(
            """
            INSERT INTO messages (conversation_id, role, content, status)
            VALUES (%s, 'assistant', %s, 'completed')
            RETURNING id, created_at
            """,
            (conversation_id, text),
        ).fetchone()
        message_id = str(row["id"])

        conn.execute("UPDATE conversations SET updated_at = now() WHERE id = %s", (conversation_id,))
        _notify(
            conn, company_id, conversation_id, "conversation.agent_message",
            {"message_id": message_id, "text": text, "actor_user_id": actor_user_id},
        )
        return {"message_id": message_id, "created_at": row["created_at"].isoformat()}


def hand_off(company_id: str, conversation_id: str, assigned_to: str | None = None) -> dict:
    status = "assigned" if assigned_to else "queued"
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE conversations
            SET status = %s, assigned_to = %s, handed_off_at = now(), updated_at = now()
            WHERE id = %s AND bot_id IN (SELECT id FROM bots WHERE company_id = %s)
            RETURNING id, status, assigned_to, handed_off_at
            """,
            (status, assigned_to, conversation_id, company_id),
        ).fetchone()
        if not row:
            return {"error": "Conversation not found"}
        _notify(conn, company_id, conversation_id, "conversation.handoff_requested")
        return dict(row)


def assign(company_id: str, conversation_id: str, user_id: str) -> dict:
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE conversations
            SET status = 'assigned', assigned_to = %s, updated_at = now()
            WHERE id = %s AND bot_id IN (SELECT id FROM bots WHERE company_id = %s)
            RETURNING id, status, assigned_to
            """,
            (user_id, conversation_id, company_id),
        ).fetchone()
        if not row:
            return {"error": "Conversation not found"}
        _notify(conn, company_id, conversation_id, "conversation.assigned")
        return dict(row)


def resolve(company_id: str, conversation_id: str) -> dict:
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE conversations
            SET status = 'resolved', updated_at = now()
            WHERE id = %s AND bot_id IN (SELECT id FROM bots WHERE company_id = %s)
            RETURNING id, status
            """,
            (conversation_id, company_id),
        ).fetchone()
        if not row:
            return {"error": "Conversation not found"}
        _notify(conn, company_id, conversation_id, "conversation.resolved")
        return dict(row)


def return_to_bot(company_id: str, conversation_id: str) -> dict:
    with connection() as conn:
        row = conn.execute(
            """
            UPDATE conversations
            SET status = 'bot', assigned_to = NULL, handed_off_at = NULL, updated_at = now()
            WHERE id = %s AND bot_id IN (SELECT id FROM bots WHERE company_id = %s)
            RETURNING id, status
            """,
            (conversation_id, company_id),
        ).fetchone()
        if not row:
            return {"error": "Conversation not found"}
        _notify(conn, company_id, conversation_id, "conversation.returned_to_bot")
        return dict(row)


def list_queued(company_id: str) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.status, c.assigned_to, c.handed_off_at, c.updated_at,
                   b.draft_config->>'name' AS bot_name
            FROM conversations c
            JOIN bots b ON b.id = c.bot_id
            WHERE b.company_id = %s AND c.status IN ('queued', 'assigned')
            ORDER BY c.handed_off_at ASC
            """,
            (company_id,),
        ).fetchall()
        return [dict(r) for r in rows]


# --- Canned replies ---

def create_canned_reply(company_id: str, title: str, body: str, shortcut: str | None = None) -> dict:
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO canned_replies (company_id, title, body, shortcut)
            VALUES (%s, %s, %s, %s)
            RETURNING id, title, body, shortcut, sort_order, active
            """,
            (company_id, title, body, shortcut),
        ).fetchone()
        return dict(row)


def list_canned_replies(company_id: str) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT id, title, body, shortcut, sort_order, active FROM canned_replies WHERE company_id = %s AND active = true ORDER BY sort_order, title",
            (company_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_canned_reply(company_id: str, reply_id: str, **updates) -> dict | None:
    allowed = {"title", "body", "shortcut", "sort_order", "active"}
    sets = []
    vals = []
    for k, v in updates.items():
        if k in allowed:
            sets.append(f"{k} = %s")
            vals.append(v)
    if not sets:
        return None
    vals.extend([reply_id, company_id])
    with connection() as conn:
        row = conn.execute(
            f"UPDATE canned_replies SET {', '.join(sets)} WHERE id = %s AND company_id = %s RETURNING id, title, body, shortcut, sort_order, active",
            vals,
        ).fetchone()
        return dict(row) if row else None


def delete_canned_reply(company_id: str, reply_id: str) -> bool:
    with connection() as conn:
        result = conn.execute(
            "DELETE FROM canned_replies WHERE id = %s AND company_id = %s",
            (reply_id, company_id),
        )
        return result.rowcount > 0
