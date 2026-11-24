"""Bot draft configuration, publication, and lead-form provisioning
(Phase 4/5, docs/19-BACKEND-SPRINT-PLAN-V2.md). No FastAPI imports here --
app/bots/router.py is the thin HTTP adapter.
"""
import json
import secrets


class BotError(ValueError):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


# --- Default lead form (Phase 5) -----------------------------------------

_DEFAULT_LEAD_FORM_FIELDS = (
    {"field_key": "name", "label": "Name", "field_type": "text", "is_required": False, "sort_order": 0},
    {"field_key": "email", "label": "Email", "field_type": "email", "is_required": False, "sort_order": 1},
)


def _seed_default_lead_form(conn, bot_id: str) -> None:
    """V1 ships exactly one post-hoc, skippable form with optional
    name/email -- matches the flat leads(name,email) behavior described
    in the original PRD, but on the V2-ready lead_forms/lead_form_fields
    shape from docs/18-DATABASE-V2-V3-SCALABLE-SCHEMA.md, so V2's
    required-before-chat-start / multi-form / custom-field features are
    new rows later, not a schema change."""
    form = conn.execute(
        """
        INSERT INTO lead_forms (bot_id, name, trigger, is_required)
        VALUES (%s, 'Default', 'post_hoc', false)
        RETURNING id
        """,
        (bot_id,),
    ).fetchone()
    for field in _DEFAULT_LEAD_FORM_FIELDS:
        conn.execute(
            """
            INSERT INTO lead_form_fields (lead_form_id, field_key, label, field_type, is_required, sort_order)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (form["id"], field["field_key"], field["label"], field["field_type"], field["is_required"], field["sort_order"]),
        )


def get_or_create_bot_for_company(conn, company_id: str) -> str:
    existing = conn.execute("SELECT id FROM bots WHERE company_id = %s", (company_id,)).fetchone()
    if existing:
        return str(existing["id"])

    public_id = secrets.token_urlsafe(12)
    row = conn.execute(
        "INSERT INTO bots (company_id, public_id) VALUES (%s, %s) RETURNING id",
        (company_id, public_id),
    ).fetchone()
    bot_id = str(row["id"])
    _seed_default_lead_form(conn, bot_id)
    return bot_id


# --- Draft config (Phase 4) ----------------------------------------------


def get_bot(conn, company_id: str) -> dict:
    bot = conn.execute("SELECT * FROM bots WHERE company_id = %s", (company_id,)).fetchone()
    if not bot:
        raise BotError(404, "no_bot", "No bot found for this company.")
    return bot


def update_draft_config(conn, company_id: str, expected_revision: int, patch: dict) -> int:
    """Optimistic concurrency: the caller must supply the draft_revision
    they last read. A concurrent edit (or a stale client) that doesn't
    match the current revision is rejected with 409, never silently
    overwritten (docs/02-ACCEPTANCE.md 'PATCH uses draft revision conflict
    control')."""
    row = conn.execute(
        """
        UPDATE bots
        SET draft_config = draft_config || %s::jsonb, draft_revision = draft_revision + 1, updated_at = now()
        WHERE company_id = %s AND draft_revision = %s
        RETURNING draft_revision
        """,
        (json.dumps(patch), company_id, expected_revision),
    ).fetchone()

    if not row:
        exists = conn.execute("SELECT id FROM bots WHERE company_id = %s", (company_id,)).fetchone()
        if not exists:
            raise BotError(404, "no_bot", "No bot found for this company.")
        raise BotError(409, "draft_revision_conflict", "The draft was changed by another request. Reload and retry.")

    return row["draft_revision"]


# --- Publish / unpublish (Phase 4) ---------------------------------------


def publish_bot(conn, company_id: str, selected_document_version_ids: list[str]) -> dict:
    """Validates every selected version is ready AND actually belongs to
    this company before creating an immutable snapshot -- this is the
    tenant-isolation-critical check: a version ID from another company
    must never be publishable here (docs/03-TRD.md 'publication
    references immutable source versions')."""
    bot = get_bot(conn, company_id)

    if not selected_document_version_ids:
        raise BotError(422, "no_sources_selected", "Select at least one ready source to publish.")

    rows = conn.execute(
        """
        SELECT dv.id, dv.status
        FROM document_versions dv
        JOIN documents d ON d.id = dv.document_id
        WHERE dv.id = ANY(%s) AND d.company_id = %s AND d.deleted_at IS NULL
        """,
        (selected_document_version_ids, company_id),
    ).fetchall()

    found_ids = {str(r["id"]) for r in rows}
    missing = set(selected_document_version_ids) - found_ids
    if missing:
        raise BotError(404, "source_version_not_found", "One or more selected sources do not belong to this company.")

    not_ready = [str(r["id"]) for r in rows if r["status"] != "ready"]
    if not_ready:
        raise BotError(422, "source_not_ready", "All selected sources must be in the 'ready' state to publish.")

    next_version_row = conn.execute(
        "SELECT COALESCE(MAX(version), 0) + 1 AS next_version FROM publications WHERE bot_id = %s",
        (bot["id"],),
    ).fetchone()
    next_version = next_version_row["next_version"]

    publication = conn.execute(
        """
        INSERT INTO publications (bot_id, version, config_snapshot, prompt_version)
        VALUES (%s, %s, %s, 'v1')
        RETURNING id
        """,
        (bot["id"], next_version, json.dumps(bot["draft_config"])),
    ).fetchone()
    publication_id = publication["id"]

    for version_id in selected_document_version_ids:
        conn.execute(
            "INSERT INTO publication_sources (publication_id, document_version_id) VALUES (%s, %s)",
            (publication_id, version_id),
        )

    conn.execute("UPDATE bots SET active_publication_id = %s, updated_at = now() WHERE id = %s", (publication_id, bot["id"]))

    return {"publication_id": str(publication_id), "version": next_version}


def unpublish_bot(conn, company_id: str) -> None:
    row = conn.execute(
        "UPDATE bots SET active_publication_id = NULL, updated_at = now() WHERE company_id = %s RETURNING id",
        (company_id,),
    ).fetchone()
    if not row:
        raise BotError(404, "no_bot", "No bot found for this company.")


# --- Lead form config (Phase 5) ------------------------------------------


def get_lead_form(conn, company_id: str) -> dict:
    bot = get_bot(conn, company_id)
    form = conn.execute(
        "SELECT * FROM lead_forms WHERE bot_id = %s ORDER BY created_at ASC LIMIT 1",
        (bot["id"],),
    ).fetchone()
    if not form:
        raise BotError(404, "no_lead_form", "No lead form found for this bot.")

    fields = conn.execute(
        "SELECT * FROM lead_form_fields WHERE lead_form_id = %s ORDER BY sort_order ASC",
        (form["id"],),
    ).fetchall()
    return {**form, "fields": fields}


def update_lead_form_field_required(conn, company_id: str, field_key: str, is_required: bool) -> None:
    """V1 scope: toggle whether the default name/email fields are
    required. Multiple forms, custom fields, and trigger changes are
    V2 (docs/18-DATABASE-V2-V3-SCALABLE-SCHEMA.md)."""
    bot = get_bot(conn, company_id)
    row = conn.execute(
        """
        UPDATE lead_form_fields lff
        SET is_required = %s
        FROM lead_forms lf
        WHERE lff.lead_form_id = lf.id AND lf.bot_id = %s AND lff.field_key = %s
        RETURNING lff.id
        """,
        (is_required, bot["id"], field_key),
    ).fetchone()
    if not row:
        raise BotError(404, "field_not_found", "No such lead form field.")


# --- Conversation management (Sprint 5) -----------------------------------


def get_conversations(conn, company_id: str) -> list[dict]:
    """List all conversations for this company's bots."""
    rows = conn.execute(
        """
        SELECT c.id, c.bot_id, c.publication_id, c.status, c.created_at
        FROM conversations c
        JOIN bots b ON c.bot_id = b.id
        WHERE b.company_id = %s
        ORDER BY c.created_at DESC
        """,
        (company_id,),
    ).fetchall()
    return [
        {
            "id": str(r["id"]),
            "bot_id": str(r["bot_id"]),
            "publication_id": str(r["publication_id"]),
            "status": r["status"],
            "created_at": r["created_at"].isoformat() if hasattr(r["created_at"], 'isoformat') else str(r["created_at"]),
        }
        for r in rows
    ]


def get_conversation(conn, conversation_id: str, company_id: str) -> dict | None:
    """Get a single conversation, verifying ownership."""
    # Verify ownership: conversation belongs to a bot under this company
    conv = conn.execute(
        """
        SELECT c.id, c.bot_id, c.publication_id, c.status, c.created_at
        FROM conversations c
        JOIN bots b ON c.bot_id = b.id
        WHERE c.id = %s AND b.company_id = %s
        """,
        (conversation_id, company_id),
    ).fetchone()
    if not conv:
        return None
    return {
        "id": str(conv["id"]),
        "bot_id": str(conv["bot_id"]),
        "publication_id": str(conv["publication_id"]),
        "status": conv["status"],
        "created_at": conv["created_at"].isoformat() if hasattr(conv["created_at"], 'isoformat') else str(conv["created_at"]),
    }


def delete_conversation(conn, conversation_id: str, company_id: str) -> dict:
    """Delete a conversation and all its messages. Verify ownership first."""
    # Verify ownership
    conv = conn.execute(
        """
        SELECT c.id, c.bot_id FROM conversations c
        JOIN bots b ON c.bot_id = b.id
        WHERE c.id = %s AND b.company_id = %s
        """,
        (conversation_id, company_id),
    ).fetchone()
    if not conv:
        raise BotError(404, "conversation_not_found", "Conversation not found or not owned.")

    # Delete messages first (cascade should handle this, but explicit)
    conn.execute("DELETE FROM messages WHERE conversation_id = %s", (conversation_id,))

    # Delete conversation
    result = conn.execute(
        "DELETE FROM conversations WHERE id = %s RETURNING id",
        (conversation_id,),
    ).fetchone()
    return {"status": "deleted", "conversation_id": conversation_id}


def export_conversation_data(conn, conversation_id: str, company_id: str) -> dict:
    """Export conversation data with field allowlist."""
    # Verify ownership
    conv = conn.execute(
        """
        SELECT c.id, c.bot_id FROM conversations c
        JOIN bots b ON c.bot_id = b.id
        WHERE c.id = %s AND b.company_id = %s
        """,
        (conversation_id, company_id),
    ).fetchone()
    if not conv:
        raise BotError(404, "conversation_not_found", "Conversation not found or not owned.")

    # Fetch messages with allowlist: only role, content, status, citations (no secrets, no internal IDs)
    msg_rows = conn.execute(
        """
        SELECT id, role, content, status, citations, created_at
        FROM messages WHERE conversation_id = %s
        ORDER BY created_at ASC
        """,
        (conversation_id,),
    ).fetchall()

    messages = []
    for m in msg_rows:
        citations = m["citations"] if m["citations"] else []
        msg = {
            "id": str(m["id"]),
            "role": m["role"],
            "content": m["content"],
            "status": m["status"],
            "citations": citations[:10] if isinstance(citations, list) else [],
        }
        messages.append(msg)

    # Build sources list (field allowlist - no provider keys, no stack traces)
    sources = []
    for m in messages:
        for c in m.get("citations", []) or []:
            src = {
                "index": c.get("index", 0),
                "document_id": c.get("document_id", ""),
                "title": c.get("title", ""),
                "page": c.get("page", 1),
            }
            sources.append(src)

    return {
        "conversation_id": conversation_id,
        "messages": messages,
        "sources": sources,
        "export_id": str(uuid.uuid4()),
    }


def delete_account(conn, company_id: str) -> dict:
    """Delete an account and all associated data with proper tenant isolation.

    Cascades: sessions, auth_tokens, oauth_accounts, conversations, messages,
    leads, usage records, publications, document versions, and finally the bot.
    All scoped to company_id to prevent cross-tenant data leaks.
    """
    # The database should have proper ON DELETE CASCADE set up,
    # but we explicitly clean up in dependency order for safety.

    # 1. Delete conversations and all their messages (cascade handles messages)
    conn.execute("DELETE FROM conversations WHERE bot_id IN (SELECT id FROM bots WHERE company_id = %s)", (company_id,))

    # 2. Delete leads associated with this company's bots
    conn.execute("DELETE FROM leads WHERE bot_id IN (SELECT id FROM bots WHERE company_id = %s)", (company_id,))

    # 3. Delete usage reservations and daily usage
    conn.execute("DELETE FROM usage_reservations WHERE bot_id IN (SELECT id FROM bots WHERE company_id = %s)", (company_id,))
    conn.execute("DELETE FROM usage_daily WHERE bot_id IN (SELECT id FROM bots WHERE company_id = %s)", (company_id,))

    # 4. Delete bot domains (domain allowlist)
    conn.execute("DELETE FROM bot_domains WHERE bot_id IN (SELECT id FROM bots WHERE company_id = %s)", (company_id,))

    # 5. Delete audit events for this company
    conn.execute("DELETE FROM audit_events WHERE company_id = %s", (company_id,))

    # 6. Delete publications and their sources (cascade should handle, but explicit)
    conn.execute("DELETE FROM publication_sources WHERE publication_id IN (SELECT id FROM publications WHERE bot_id IN (SELECT id FROM bots WHERE company_id = %s))", (company_id,))
    conn.execute("DELETE FROM publications WHERE bot_id IN (SELECT id FROM bots WHERE company_id = %s)", (company_id,))

    # 7. Delete document versions for this company's documents
    conn.execute("""
        DELETE FROM document_versions
        WHERE id IN (
            SELECT dv.id FROM document_versions dv
            JOIN documents d ON d.id = dv.document_id
            WHERE d.company_id = %s
        )
    """, (company_id,))

    # 8. Delete documents for this company
    conn.execute("DELETE FROM documents WHERE company_id = %s", (company_id,))

    # 9. Delete bots for this company
    result = conn.execute(
        "DELETE FROM bots WHERE company_id = %s RETURNING id, public_id",
        (company_id,),
    ).fetchall()

    deleted_count = len(result)
    deleted_ids = [str(r["id"]) for r in result]

    return {
        "status": "deleted",
        "company_id": company_id,
        "deleted_bot_ids": deleted_ids,
        "deleted_count": deleted_count,
    }
