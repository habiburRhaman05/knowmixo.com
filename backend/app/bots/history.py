"""Owner conversation history, domain allowlist, embed/export surfaces and
tenant data purge (docs/16-API-ROUTES.md "Conversation history (owner)",
docs/14 Sprint 5). Every query is scoped through bots.company_id derived
from the authenticated session -- IDs from the client are only ever used
as lookups INSIDE that scope, so ID substitution yields 404, never data.

Exports are built from explicit field allowlists (never `SELECT *` /
dict dumps), so provider keys, webhook secrets and internal ids cannot be
included by construction.
"""
import base64
import json
import re
import uuid
from datetime import datetime

from app.bots.service import BotError
from app.config import settings

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 25
MAX_DOMAINS = 20
_DOMAIN_RE = re.compile(r"^(\*\.)?([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$|^localhost$")


# --- Cursor pagination ------------------------------------------------------


def encode_cursor(created_at: datetime, row_id: str) -> str:
    return base64.urlsafe_b64encode(f"{created_at.isoformat()}|{row_id}".encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts, row_id = raw.split("|", 1)
        uuid.UUID(row_id)
        return datetime.fromisoformat(ts), row_id
    except (ValueError, TypeError) as exc:
        raise BotError(400, "invalid_cursor", "Invalid pagination cursor.") from exc


# --- Conversations ----------------------------------------------------------


def _build_conversation_filters(
    company_id: str,
    date_from: datetime | None,
    date_to: datetime | None,
    status: str | None,
    has_feedback: bool | None,
    tags: list[str] | None,
) -> tuple[list[str], list]:
    where = ["b.company_id = %s", "NOT c.is_preview"]
    params: list = [company_id]
    if date_from:
        where.append("c.created_at >= %s")
        params.append(date_from)
    if date_to:
        where.append("c.created_at <= %s")
        params.append(date_to)
    if status:
        # NOTE: this column's semantics changed in migration 0022 from a
        # conversation-lifecycle flag ('active'/'closed', never actually
        # written anywhere) to the handoff state machine ('bot'/'queued'/
        # 'assigned'/'resolved'). The filter below reflects current reality.
        if status not in ("bot", "queued", "assigned", "resolved"):
            raise BotError(422, "invalid_status", "status must be one of: bot, queued, assigned, resolved.")
        where.append("c.status = %s")
        params.append(status)
    feedback_exists = "EXISTS (SELECT 1 FROM feedback f JOIN messages fm ON fm.id = f.message_id WHERE fm.conversation_id = c.id)"
    if has_feedback is True:
        where.append(feedback_exists)
    elif has_feedback is False:
        where.append(f"NOT {feedback_exists}")
    if tags:
        where.append("c.tags && %s::text[]")
        params.append(tags)
    return where, params


def list_conversations(
    conn,
    company_id: str,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    status: str | None = None,
    has_feedback: bool | None = None,
    tags: list[str] | None = None,
    cursor: str | None = None,
    limit: int = DEFAULT_PAGE_SIZE,
) -> dict:
    limit = max(1, min(limit, MAX_PAGE_SIZE))
    where, params = _build_conversation_filters(company_id, date_from, date_to, status, has_feedback, tags)
    feedback_exists = "EXISTS (SELECT 1 FROM feedback f JOIN messages fm ON fm.id = f.message_id WHERE fm.conversation_id = c.id)"
    if cursor:
        ts, row_id = decode_cursor(cursor)
        where.append("(c.created_at, c.id) < (%s, %s::uuid)")
        params.extend([ts, row_id])

    rows = conn.execute(
        f"""
        SELECT c.id, c.status, c.tags, c.created_at, c.updated_at,
               (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count,
               {feedback_exists} AS has_feedback,
               EXISTS (SELECT 1 FROM leads l WHERE l.conversation_id = c.id) AS has_lead
        FROM conversations c JOIN bots b ON b.id = c.bot_id
        WHERE {' AND '.join(where)}
        ORDER BY c.created_at DESC, c.id DESC
        LIMIT %s
        """,
        (*params, limit + 1),
    ).fetchall()

    page = rows[:limit]
    next_cursor = encode_cursor(page[-1]["created_at"], str(page[-1]["id"])) if len(rows) > limit else None
    return {
        "items": [
            {
                "id": str(r["id"]),
                "status": r["status"],
                "tags": r["tags"] or [],
                "created_at": r["created_at"].isoformat(),
                "updated_at": r["updated_at"].isoformat(),
                "message_count": int(r["message_count"]),
                "has_feedback": bool(r["has_feedback"]),
                "has_lead": bool(r["has_lead"]),
            }
            for r in page
        ],
        "next_cursor": next_cursor,
    }


MAX_EXPORT_ROWS = 10_000


def export_conversations_csv(
    conn,
    company_id: str,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    status: str | None = None,
    has_feedback: bool | None = None,
    tags: list[str] | None = None,
) -> str:
    """Returns CSV text (never a row count over MAX_EXPORT_ROWS -- a
    filtered date range is expected for anything larger; this is an
    on-demand export, not a background job)."""
    import csv
    import io

    where, params = _build_conversation_filters(company_id, date_from, date_to, status, has_feedback, tags)
    feedback_exists = "EXISTS (SELECT 1 FROM feedback f JOIN messages fm ON fm.id = f.message_id WHERE fm.conversation_id = c.id)"
    rows = conn.execute(
        f"""
        SELECT c.id, c.status, c.tags, c.created_at, c.updated_at,
               (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count,
               {feedback_exists} AS has_feedback,
               EXISTS (SELECT 1 FROM leads l WHERE l.conversation_id = c.id) AS has_lead
        FROM conversations c JOIN bots b ON b.id = c.bot_id
        WHERE {' AND '.join(where)}
        ORDER BY c.created_at DESC
        LIMIT %s
        """,
        (*params, MAX_EXPORT_ROWS),
    ).fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["conversation_id", "status", "tags", "created_at", "updated_at", "message_count", "has_feedback", "has_lead"])
    for r in rows:
        writer.writerow([
            str(r["id"]), r["status"], ";".join(r["tags"] or []),
            r["created_at"].isoformat(), r["updated_at"].isoformat(),
            r["message_count"], r["has_feedback"], r["has_lead"],
        ])
    return buf.getvalue()


def set_conversation_tags(conn, company_id: str, conversation_id: str, tags: list[str]) -> list[str]:
    cleaned = sorted({t.strip() for t in tags if t.strip()})[:50]
    row = conn.execute(
        """
        UPDATE conversations c SET tags = %s::text[], updated_at = now()
        FROM bots b
        WHERE c.bot_id = b.id AND c.id = %s AND b.company_id = %s
        RETURNING c.tags
        """,
        (cleaned, conversation_id, company_id),
    ).fetchone()
    if not row:
        raise BotError(404, "conversation_not_found", "Conversation not found.")
    return row["tags"] or []


def get_conversation_detail(conn, company_id: str, conversation_id: str) -> dict:
    try:
        uuid.UUID(conversation_id)
    except ValueError as exc:
        raise BotError(404, "conversation_not_found", "Conversation not found.") from exc
    conv = conn.execute(
        """
        SELECT c.id, c.status, c.created_at FROM conversations c JOIN bots b ON b.id = c.bot_id
        WHERE c.id = %s AND b.company_id = %s AND NOT c.is_preview
        """,
        (conversation_id, company_id),
    ).fetchone()
    if not conv:
        raise BotError(404, "conversation_not_found", "Conversation not found.")

    rows = conn.execute(
        """
        SELECT m.id, m.role, m.content, m.status, m.citations, m.created_at,
               (SELECT f.rating FROM feedback f WHERE f.message_id = m.id AND f.actor = 'visitor' LIMIT 1) AS rating
        FROM messages m WHERE m.conversation_id = %s ORDER BY m.created_at ASC, m.id ASC
        """,
        (conversation_id,),
    ).fetchall()
    messages, citations = [], []
    for m in rows:
        cites = m["citations"] if isinstance(m["citations"], list) else []
        messages.append(
            {
                "id": str(m["id"]),
                "role": m["role"],
                "content": m["content"],
                "status": m["status"],
                "citations": cites,
                "feedback_rating": m["rating"],
                "created_at": m["created_at"].isoformat(),
            }
        )
        citations.extend(cites)

    lead = conn.execute(
        'SELECT "values", consent_at, submitted_at FROM leads WHERE conversation_id = %s', (conversation_id,)
    ).fetchone()
    return {
        "id": str(conv["id"]),
        "status": conv["status"],
        "created_at": conv["created_at"].isoformat(),
        "messages": messages,
        "citations": citations,
        "lead": (
            {
                "values": lead["values"],
                "consent_at": lead["consent_at"].isoformat() if lead["consent_at"] else None,
                "submitted_at": lead["submitted_at"].isoformat(),
            }
            if lead
            else None
        ),
    }


def delete_conversation(conn, company_id: str, conversation_id: str) -> None:
    """Cascades to messages, feedback and the lead; cached answers do not
    exist yet in V1 (no answer cache table)."""
    try:
        uuid.UUID(conversation_id)
    except ValueError as exc:
        raise BotError(404, "conversation_not_found", "Conversation not found.") from exc
    row = conn.execute(
        """
        DELETE FROM conversations c USING bots b
        WHERE c.id = %s AND c.bot_id = b.id AND b.company_id = %s RETURNING c.id
        """,
        (conversation_id, company_id),
    ).fetchone()
    if not row:
        raise BotError(404, "conversation_not_found", "Conversation not found.")


# --- Domain allowlist -------------------------------------------------------


def normalize_domains(domains: list[str]) -> list[str]:
    cleaned: list[str] = []
    for raw in domains:
        d = (raw or "").strip().lower()
        if not _DOMAIN_RE.match(d):
            raise BotError(422, "invalid_domain", f"'{raw}' is not a valid domain (use example.com or *.example.com, no scheme or path).")
        if d not in cleaned:
            cleaned.append(d)
    if len(cleaned) > MAX_DOMAINS:
        raise BotError(422, "too_many_domains", f"At most {MAX_DOMAINS} domains are allowed.")
    return cleaned


def replace_domains(conn, company_id: str, domains: list[str]) -> list[str]:
    cleaned = normalize_domains(domains)
    bot = conn.execute("SELECT id FROM bots WHERE company_id = %s", (company_id,)).fetchone()
    if not bot:
        raise BotError(404, "no_bot", "No bot found for this company.")
    conn.execute("DELETE FROM bot_domains WHERE bot_id = %s", (bot["id"],))
    for d in cleaned:
        conn.execute("INSERT INTO bot_domains (bot_id, domain) VALUES (%s, %s)", (bot["id"], d))
    return cleaned


def get_domains(conn, company_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT d.domain FROM bot_domains d JOIN bots b ON b.id = d.bot_id WHERE b.company_id = %s ORDER BY d.domain",
        (company_id,),
    ).fetchall()
    return [r["domain"] for r in rows]


# --- Embed + export ---------------------------------------------------------


def embed_snippets(public_id: str) -> dict:
    """Public ids only: no tokens, keys or company ids."""
    base = settings().public_app_url.rstrip("/")
    api = settings().backend_internal_url.rstrip("/")
    return {
        "public_id": public_id,
        "script_snippet": f'<script src="{base}/embed.js" data-bot-id="{public_id}" data-api="{api}" async></script>',
        "react_snippet": f'import {{ KnowmivoChat }} from "@knowmivo/react";\n\n<KnowmivoChat botId="{public_id}" />',
        "nextjs_snippet": (
            'import Script from "next/script";\n\n'
            f'<Script src="{base}/embed.js" data-bot-id="{public_id}" data-api="{api}" strategy="lazyOnload" />'
        ),
        "hosted_chat_url": f"{base}/chat/{public_id}",
    }


def bot_export(conn, company_id: str) -> dict:
    bot = conn.execute(
        "SELECT id, public_id, draft_config, draft_revision, active_publication_id FROM bots WHERE company_id = %s",
        (company_id,),
    ).fetchone()
    if not bot:
        raise BotError(404, "no_bot", "No bot found for this company.")
    publication = None
    if bot["active_publication_id"]:
        p = conn.execute(
            "SELECT version, config_snapshot, created_at FROM publications WHERE id = %s", (bot["active_publication_id"],)
        ).fetchone()
        if p:
            publication = {"version": p["version"], "config_snapshot": p["config_snapshot"], "published_at": p["created_at"].isoformat()}
    form = conn.execute("SELECT id, name, trigger, is_required FROM lead_forms WHERE bot_id = %s ORDER BY created_at LIMIT 1", (bot["id"],)).fetchone()
    fields = []
    if form:
        fields = [
            {"field_key": f["field_key"], "label": f["label"], "field_type": f["field_type"], "is_required": f["is_required"]}
            for f in conn.execute(
                "SELECT field_key, label, field_type, is_required FROM lead_form_fields WHERE lead_form_id = %s ORDER BY sort_order",
                (form["id"],),
            ).fetchall()
        ]
    return {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "bot": {"public_id": bot["public_id"], "draft_config": bot["draft_config"], "draft_revision": bot["draft_revision"]},
        "active_publication": publication,
        "allowed_domains": get_domains(conn, company_id),
        "lead_form": {"name": form["name"], "trigger": form["trigger"], "is_required": form["is_required"], "fields": fields} if form else None,
    }


def _bot_export_or_none(conn, company_id: str) -> dict | None:
    try:
        return bot_export(conn, company_id)
    except BotError:
        return None  # a company that never created a bot still exports its profile


def company_export(conn, company_id: str) -> dict:
    company = conn.execute("SELECT name, website, industry, contact FROM companies WHERE id = %s", (company_id,)).fetchone()
    if not company:
        raise BotError(404, "no_company", "No company found.")
    docs = conn.execute(
        """
        SELECT d.title, d.kind, d.source_url, d.created_at, dv.status, dv.chunk_count
        FROM documents d LEFT JOIN document_versions dv ON dv.id = d.active_version_id
        WHERE d.company_id = %s AND d.deleted_at IS NULL ORDER BY d.created_at
        """,
        (company_id,),
    ).fetchall()
    conv_ids = [
        str(r["id"])
        for r in conn.execute(
            "SELECT c.id FROM conversations c JOIN bots b ON b.id = c.bot_id WHERE b.company_id = %s AND NOT c.is_preview ORDER BY c.created_at",
            (company_id,),
        ).fetchall()
    ]
    return {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "company": {"name": company["name"], "website": company["website"], "industry": company["industry"], "contact": company["contact"]},
        "bot": _bot_export_or_none(conn, company_id),
        "documents": [
            {
                "title": d["title"],
                "kind": d["kind"],
                "source_url": d["source_url"],
                "status": d["status"],
                "chunk_count": d["chunk_count"],
                "created_at": d["created_at"].isoformat(),
            }
            for d in docs
        ],
        "conversations": [get_conversation_detail(conn, company_id, cid) for cid in conv_ids],
    }


def export_json_bytes(payload: dict) -> bytes:
    return json.dumps(payload, indent=2, default=str).encode()


# --- Tenant data purge (account deletion cleanup) ---------------------------


def purge_company_data(conn, company_id: str) -> dict:
    """Hard-deletes everything a company owns EXCEPT the company/user rows
    (those are soft-deleted by auth). Explicit dependency order because
    conversations.publication_id and publication_sources.document_version_id
    are ON DELETE RESTRICT. Every statement is scoped by company_id."""
    bots = "SELECT id FROM bots WHERE company_id = %s"
    conn.execute(f"DELETE FROM conversations WHERE bot_id IN ({bots})", (company_id,))
    for table in ("analytics_events", "usage_reservations", "usage_daily", "idempotency_keys", "crawl_jobs", "audit_events"):
        conn.execute(f"DELETE FROM {table} WHERE company_id = %s", (company_id,))
    conn.execute("UPDATE bots SET active_publication_id = NULL WHERE company_id = %s", (company_id,))
    conn.execute(f"DELETE FROM publications WHERE bot_id IN ({bots})", (company_id,))
    conn.execute("DELETE FROM jobs WHERE company_id = %s AND kind <> 'company_cleanup'", (company_id,))
    docs = conn.execute("DELETE FROM documents WHERE company_id = %s RETURNING id", (company_id,)).fetchall()
    conn.execute("DELETE FROM webhook_endpoints WHERE company_id = %s", (company_id,))
    deleted_bots = conn.execute("DELETE FROM bots WHERE company_id = %s RETURNING id", (company_id,)).fetchall()
    return {"deleted_documents": len(docs), "deleted_bots": len(deleted_bots)}
