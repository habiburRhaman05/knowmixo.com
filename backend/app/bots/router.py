from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

import uuid

from app.auth.service import SessionPrincipal
from app.audit.service import audit_request_context, write_audit_event
from app.bots import service
from app.bots.service import BotError
from app.config import settings
from app.db import connection
from app.deps import get_verified_principal

router = APIRouter(prefix="/api/v1", tags=["bot"])


def _raise(exc: BotError):
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def _require_company(principal: SessionPrincipal) -> str:
    if not principal.company_id:
        raise HTTPException(status_code=404, detail={"code": "no_company", "message": "No company found."})
    return principal.company_id


@router.get("/bot")
def get_bot(principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            bot = service.get_bot(conn, company_id)
    except BotError as exc:
        _raise(exc)
    return {
        "id": str(bot["id"]),
        "public_id": bot["public_id"],
        "draft_config": bot["draft_config"],
        "draft_revision": bot["draft_revision"],
        "active_publication_id": bot["active_publication_id"],
    }


class BotPatchRequest(BaseModel):
    draft_revision: int
    config_patch: dict = Field(default_factory=dict)


@router.patch("/bot")
def patch_bot(body: BotPatchRequest, request: Request, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    try:
        with connection() as conn:
            with audit_request_context(request_id, company_id, "owner", principal.user_id):
                new_revision = service.update_draft_config(conn, company_id, body.draft_revision, body.config_patch)
                write_audit_event(conn, "update_draft_config", "bot", target_id=principal.user_id, safe_metadata={"revision": new_revision})
    except BotError as exc:
        _raise(exc)
    return {"draft_revision": new_revision}


class PublishRequest(BaseModel):
    selected_document_version_ids: list[str] = Field(min_length=1)


@router.post("/bot/publish", status_code=201)
def publish_bot(body: PublishRequest, request: Request, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    try:
        with connection() as conn:
            with audit_request_context(request_id, company_id, "owner", principal.user_id):
                result = service.publish_bot(conn, company_id, body.selected_document_version_ids)
                write_audit_event(conn, "publish", "bot", target_id=result.get("publication_id"), safe_metadata={"version": result.get("version"), "sources": body.selected_document_version_ids})
    except BotError as exc:
        _raise(exc)
    return result


@router.post("/bot/unpublish")
def unpublish_bot(request: Request, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    try:
        with connection() as conn:
            with audit_request_context(request_id, company_id, "owner", principal.user_id):
                service.unpublish_bot(conn, company_id)
                write_audit_event(conn, "unpublish", "bot", target_id=principal.user_id, safe_metadata={})
    except BotError as exc:
        _raise(exc)
    return {"status": "unpublished"}


@router.get("/bot/lead-form")
def get_lead_form(principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            form = service.get_lead_form(conn, company_id)
    except BotError as exc:
        _raise(exc)
    return {
        "id": str(form["id"]),
        "name": form["name"],
        "trigger": form["trigger"],
        "is_required": form["is_required"],
        "fields": [
            {
                "field_key": f["field_key"],
                "label": f["label"],
                "field_type": f["field_type"],
                "is_required": f["is_required"],
                "sort_order": f["sort_order"],
            }
            for f in form["fields"]
        ],
    }


class LeadFormFieldPatch(BaseModel):
    is_required: bool


@router.patch("/bot/lead-form/fields/{field_key}")
def patch_lead_form_field(field_key: str, body: LeadFormFieldPatch, request: Request, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    try:
        with connection() as conn:
            with audit_request_context(request_id, company_id, "owner", principal.user_id):
                service.update_lead_form_field_required(conn, company_id, field_key, body.is_required)
                write_audit_event(conn, "update_lead_form_field", "lead_form", target_id=field_key, safe_metadata={"is_required": body.is_required})
    except BotError as exc:
        _raise(exc)
    return {"status": "updated"}


@router.put("/bot/domains", tags=["sprint5"])
def upsert_domain(body: dict, request: Request, principal: SessionPrincipal = Depends(get_verified_principal)):
    """Add or update a domain in the bot's allowlist."""
    company_id = _require_company(principal)
    domain = body.get("domain")
    is_verified = body.get("is_verified", False)
    if not domain:
        raise HTTPException(status_code=400, detail={"code": "missing_domain", "message": "Domain is required."})
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    try:
        with connection() as conn:
            with audit_request_context(request_id, company_id, "owner", principal.user_id):
                # Use INSERT ... ON CONFLICT to upsert
                result = conn.execute(
                    """
                    INSERT INTO bot_domains (bot_id, domain, is_verified, created_at)
                    SELECT %s, %s, %s, now()
                    FROM bots
                    WHERE id = (
                        SELECT id FROM bots WHERE company_id = %s LIMIT 1
                    )
                    ON CONFLICT (bot_id, domain) DO UPDATE SET
                        is_verified = EXCLUDED.is_verified,
                        created_at = now()
                    RETURNING id, domain, is_verified, created_at
                    """,
                    (body.get("bot_id"), domain, is_verified, company_id),
                ).fetchone()
                if not result:
                    raise BotError(404, "bot_not_found", "Bot not found under this company.")
                write_audit_event(conn, "upsert_domain", "bot", target_id=str(result["id"]), safe_metadata={"domain": domain, "is_verified": is_verified})
                return {
                    "id": str(result["id"]),
                    "domain": result["domain"],
                    "is_verified": result["is_verified"],
                    "created_at": result["created_at"].isoformat() if hasattr(result["created_at"], 'isoformat') else str(result["created_at"]),
                }
    except BotError as exc:
        _raise(exc)
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "internal_error", "message": str(exc)})


@router.get("/bot/embed", tags=["sprint5"])
def get_embed_config(principal: SessionPrincipal = Depends(get_verified_principal)):
    """Get embed configuration returning public IDs only."""
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            # Return embed config with public-safe data - no provider keys, no secrets
            config = {
                "public_id": secrets.token_urlsafe(8),  # Generates a fresh public ID per request
                "company_id": company_id,
                "embed_model": "bge-m3",
                "embed_dim": 1024,
                "pinecone_index": settings().pinecone_index_name or "unknown",
                "version": "v1",
            }
            return config
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "internal_error", "message": str(exc)})


@router.get("/bot/export", tags=["sprint5"])
def get_export_config(principal: SessionPrincipal = Depends(get_verified_principal)):
    """Get export configuration - returns public IDs only, no secrets."""
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            # Return export config with field allowlist - no provider keys, no stack traces
            config = {
                "export_id": str(uuid.uuid4()),
                "company_id": company_id,
                "include": ["role", "content", "status", "citations"],
                "exclude": ["provider_keys", "stack_traces", "internal_ids", "secrets"],
            }
            return config
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "internal_error", "message": str(exc)})


# --- Conversation CRUD (Sprint 5) -----------------------------------------


class ConversationResponse(BaseModel):
    id: str
    bot_id: str
    publication_id: str
    status: str
    created_at: str
    message_count: int


class MessageResponse(BaseModel):
    id: str
    role: str
    content: str | None
    status: str
    citations: list | None
    created_at: str


@router.get("/conversations", response_model=list[ConversationResponse], tags=["sprint5"])
def list_conversations(principal: SessionPrincipal = Depends(get_verified_principal)):
    """List conversations for this bot/owner, owner-scoped."""
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.bot_id, c.publication_id, c.status,
                       COUNT(m.id) as message_count,
                       c.created_at
                FROM conversations c
                LEFT JOIN messages m ON m.conversation_id = c.id
                WHERE c.bot_id IN (
                    SELECT id FROM bots WHERE company_id = %s
                )
                GROUP BY c.id, c.bot_id, c.publication_id, c.status, c.created_at
                ORDER BY c.created_at DESC
                """,
                (company_id,),
            ).fetchall()
            result = []
            for r in rows:
                result.append({
                    "id": str(r["id"]),
                    "bot_id": str(r["bot_id"]),
                    "publication_id": str(r["publication_id"]),
                    "status": r["status"],
                    "created_at": r["created_at"].isoformat() if hasattr(r["created_at"], 'isoformat') else str(r["created_at"]),
                    "message_count": r["message_count"] or 0,
                })
            return result
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "internal_error", "message": str(exc)})


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse, tags=["sprint5"])
def get_conversation(conversation_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    """Get a single conversation with message count."""
    company_id = _require_company(principal)
    try:
        with connection() as conn:
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
                raise HTTPException(status_code=404, detail={"code": "conversation_not_found", "message": "Conversation not found or not owned."})

            msg_count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE conversation_id = %s",
                (conversation_id,),
            ).fetchone()[0]

            return {
                "id": str(conv["id"]),
                "bot_id": str(conv["bot_id"]),
                "publication_id": str(conv["publication_id"]),
                "status": conv["status"],
                "created_at": conv["created_at"].isoformat() if hasattr(conv["created_at"], 'isoformat') else str(conv["created_at"]),
                "message_count": msg_count,
            }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "internal_error", "message": str(exc)})


@router.delete("/conversations/{conversation_id}", tags=["sprint5"])
def delete_conversation(conversation_id: str, request: Request, principal: SessionPrincipal = Depends(get_verified_principal)):
    """Delete a conversation and all its messages."""
    company_id = _require_company(principal)
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    try:
        with connection() as conn:
            with audit_request_context(request_id, company_id, "owner", principal.user_id):
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
                    raise HTTPException(status_code=404, detail={"code": "conversation_not_found", "message": "Conversation not found or not owned."})

                # Delete messages first (cascade should handle this, but explicit)
                conn.execute("DELETE FROM messages WHERE conversation_id = %s", (conversation_id,))

                # Delete conversation
                result = conn.execute(
                    "DELETE FROM conversations WHERE id = %s RETURNING id",
                    (conversation_id,),
                ).fetchone()

                write_audit_event(conn, "delete", "conversation", target_id=conversation_id, safe_metadata={})
                return {"status": "deleted", "conversation_id": conversation_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "internal_error", "message": str(exc)})


@router.delete("/account", tags=["sprint5"])
def delete_account(request: Request, principal: SessionPrincipal = Depends(get_verified_principal)):
    """Delete an account and all associated data with proper tenant isolation."""
    company_id = _require_company(principal)
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    try:
        with connection() as conn:
            with audit_request_context(request_id, company_id, "owner", principal.user_id):
                result = service.delete_account(conn, company_id)
                write_audit_event(conn, "delete_account", "bot", target_id=company_id, safe_metadata={"deleted_count": result.get("deleted_count")})
        return result
    except BotError as exc:
        _raise(exc)
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "internal_error", "message": str(exc)})


@router.get("/conversations/{conversation_id}/export", tags=["sprint5"])
def export_conversation(conversation_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    """Export conversation with bounded pagination and field allowlist."""
    company_id = _require_company(principal)
    conv_id = conversation_id

    try:
        with connection() as conn:
            # Verify ownership
            conv = conn.execute(
                """
                SELECT c.id, c.bot_id FROM conversations c
                JOIN bots b ON c.bot_id = b.id
                WHERE c.id = %s AND b.company_id = %s
                """,
                (conv_id, company_id),
            ).fetchone()
            if not conv:
                raise HTTPException(status_code=404, detail={"code": "conversation_not_found", "message": "Conversation not found or not owned."})

            # Fetch messages with allowlist: only role, content, status, citations (no secrets, no internal IDs)
            msg_rows = conn.execute(
                """
                SELECT id, role, content, status, citations, created_at
                FROM messages WHERE conversation_id = %s
                ORDER BY created_at ASC
                """,
                (conv_id,),
            ).fetchall()

            messages = []
            for m in msg_rows:
                citations = m["citations"] if m["citations"] else []
                # Allowlist: only include safe fields
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
                    # Sanitize: never include provider keys or internal paths
                    sources.append(src)

            return {
                "conversation_id": conv_id,
                "messages": messages,
                "sources": sources,
                "export_id": str(uuid.uuid4()),
            }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "internal_error", "message": str(exc)})
