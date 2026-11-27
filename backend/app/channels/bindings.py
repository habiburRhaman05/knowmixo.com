"""bot_channel_bindings + channel_identities CRUD (D6.1/D6.4):
maps an external Meta account to a bot, and an external sender to the
synthetic visitor_session + conversation that carries their turns
through the existing chat pipeline unchanged.
"""
import logging
import secrets

from app.db import connection
from app.public.router import hash_token

log = logging.getLogger(__name__)

SYNTHETIC_SESSION_YEARS = 10


def create_binding(company_id: str, bot_id: str, channel: str, external_account_id: str) -> dict:
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO bot_channel_bindings (company_id, bot_id, channel, external_account_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (channel, external_account_id) DO UPDATE SET bot_id = EXCLUDED.bot_id, active = true
            RETURNING id, bot_id, channel, external_account_id, active
            """,
            (company_id, bot_id, channel, external_account_id),
        ).fetchone()
        return dict(row)


def list_bindings(company_id: str) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT id, bot_id, channel, external_account_id, active, created_at FROM bot_channel_bindings WHERE company_id = %s ORDER BY created_at",
            (company_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def delete_binding(company_id: str, binding_id: str) -> bool:
    with connection() as conn:
        result = conn.execute(
            "DELETE FROM bot_channel_bindings WHERE id = %s AND company_id = %s",
            (binding_id, company_id),
        )
        return result.rowcount > 0


def resolve_binding(channel: str, external_account_id: str) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            """
            SELECT b.id, b.bot_id, b.company_id
            FROM bot_channel_bindings b
            WHERE b.channel = %s AND b.external_account_id = %s AND b.active = true
            """,
            (channel, external_account_id),
        ).fetchone()
        return dict(row) if row else None


def get_or_create_channel_conversation(company_id: str, bot_id: str, channel: str, external_id: str) -> dict:
    """Returns {"conversation_id", "visitor_session_id"}, reusing the
    existing one if this external sender has written to this bot before.
    Creates a synthetic (never-expiring) visitor_session + conversation
    so the message can flow through pipeline.prepare_turn/stream_turn
    completely unchanged -- channel conversations are indistinguishable
    from widget conversations to the chat pipeline."""
    with connection() as conn:
        existing = conn.execute(
            """
            SELECT visitor_session_id, conversation_id FROM channel_identities
            WHERE bot_id = %s AND channel = %s AND external_id = %s
            """,
            (bot_id, channel, external_id),
        ).fetchone()
        if existing:
            return {"conversation_id": str(existing["conversation_id"]), "visitor_session_id": str(existing["visitor_session_id"])}

        bot = conn.execute(
            "SELECT active_publication_id FROM bots WHERE id = %s", (bot_id,)
        ).fetchone()
        if not bot or not bot["active_publication_id"]:
            raise ValueError("bot_unpublished")

        synthetic_token = secrets.token_urlsafe(32)
        session_row = conn.execute(
            """
            INSERT INTO visitor_sessions (bot_id, session_token_hash, expires_at)
            VALUES (%s, %s, now() + make_interval(years => %s))
            RETURNING id
            """,
            (bot_id, hash_token(synthetic_token), SYNTHETIC_SESSION_YEARS),
        ).fetchone()
        visitor_session_id = str(session_row["id"])

        conv_row = conn.execute(
            "INSERT INTO conversations (bot_id, publication_id, visitor_session_id) VALUES (%s, %s, %s) RETURNING id",
            (bot_id, bot["active_publication_id"], visitor_session_id),
        ).fetchone()
        conversation_id = str(conv_row["id"])

        conn.execute(
            """
            INSERT INTO channel_identities (company_id, bot_id, channel, external_id, visitor_session_id, conversation_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (company_id, bot_id, channel, external_id, visitor_session_id, conversation_id),
        )
        return {"conversation_id": conversation_id, "visitor_session_id": visitor_session_id}
