"""Public API (D9.4, ADR 007): /api/v1/public-api/*, Bearer km_live_...
auth, scoped per key, cursor pagination, RFC 9457 errors. Rate limiting
(per key, not per IP) is enforced inside app.public_api.auth.require_scope.
"""
import secrets

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field

from app.bots import history
from app.bots.service import BotError
from app.db import connection
from app.handoff import service as handoff_service
from app.idempotency import run_idempotent
from app.public_api.auth import require_scope
from app.public_api.keys import ApiKeyPrincipal
from app.public_api.problem_details import PublicAPIError
from app.sources.service import SourceError, create_text_source, create_url_source

router = APIRouter(prefix="/api/v1/public-api", tags=["public-api"])


# --- conversations:read ------------------------------------------------


@router.get("/conversations")
async def list_conversations(
    cursor: str | None = None,
    limit: int = Query(default=history.DEFAULT_PAGE_SIZE, ge=1, le=history.MAX_PAGE_SIZE),
    principal: ApiKeyPrincipal = Depends(require_scope("conversations:read")),
):
    with connection() as conn:
        try:
            return history.list_conversations(conn, principal.company_id, cursor=cursor, limit=limit)
        except BotError as exc:
            raise PublicAPIError(exc.status_code, exc.code, exc.message)


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, principal: ApiKeyPrincipal = Depends(require_scope("conversations:read"))):
    with connection() as conn:
        try:
            return history.get_conversation_detail(conn, principal.company_id, conversation_id)
        except BotError as exc:
            raise PublicAPIError(exc.status_code, exc.code, exc.message)


# --- conversations:write -------------------------------------------------


class ReplyRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)


@router.post("/conversations/{conversation_id}/reply")
async def reply_to_conversation(
    conversation_id: str,
    body: ReplyRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: ApiKeyPrincipal = Depends(require_scope("conversations:write")),
):
    try:
        with connection() as conn:
            result, _replayed = run_idempotent(
                conn, principal.company_id, "public_api_reply", idempotency_key, body.model_dump(),
                lambda: handoff_service.send_agent_reply(principal.company_id, conversation_id, body.text),
            )
        return result
    except handoff_service.HandoffError as exc:
        raise PublicAPIError(exc.status_code, exc.code, exc.message)
    except BotError as exc:
        raise PublicAPIError(exc.status_code, exc.code, exc.message)


# --- leads:read -----------------------------------------------------------


@router.get("/leads")
async def list_leads(
    cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    principal: ApiKeyPrincipal = Depends(require_scope("leads:read")),
):
    where = ["b.company_id = %s"]
    params: list = [principal.company_id]
    if cursor:
        ts, row_id = history.decode_cursor(cursor)
        where.append("(l.submitted_at, l.id) < (%s, %s::uuid)")
        params.extend([ts, row_id])

    with connection() as conn:
        rows = conn.execute(
            f"""
            SELECT l.id, l.conversation_id, l.values, l.submitted_at
            FROM leads l
            JOIN conversations c ON c.id = l.conversation_id
            JOIN bots b ON b.id = c.bot_id
            WHERE {' AND '.join(where)}
            ORDER BY l.submitted_at DESC, l.id DESC
            LIMIT %s
            """,
            (*params, limit + 1),
        ).fetchall()

    page = rows[:limit]
    next_cursor = history.encode_cursor(page[-1]["submitted_at"], str(page[-1]["id"])) if len(rows) > limit else None
    return {
        "items": [
            {"id": str(r["id"]), "conversation_id": str(r["conversation_id"]), "values": r["values"], "submitted_at": r["submitted_at"].isoformat()}
            for r in page
        ],
        "next_cursor": next_cursor,
    }


# --- sources:write ----------------------------------------------------------


class TextSourceRequest(BaseModel):
    title: str = Field(..., max_length=200)
    text: str = Field(..., min_length=1, max_length=200_000)


class UrlSourceRequest(BaseModel):
    url: str = Field(..., max_length=2000)


@router.post("/sources/text")
async def add_text_source(
    body: TextSourceRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: ApiKeyPrincipal = Depends(require_scope("sources:write")),
):
    try:
        with connection() as conn:
            result, _replayed = run_idempotent(
                conn, principal.company_id, "public_api_text_source", idempotency_key, body.model_dump(),
                lambda: dict(zip(("document_id", "job_id"), create_text_source(conn, principal.company_id, body.title, body.text))),
            )
        return result
    except SourceError as exc:
        raise PublicAPIError(exc.status_code, exc.code, exc.message)


@router.post("/sources/url")
async def add_url_source(
    body: UrlSourceRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    principal: ApiKeyPrincipal = Depends(require_scope("sources:write")),
):
    try:
        with connection() as conn:
            result, _replayed = run_idempotent(
                conn, principal.company_id, "public_api_url_source", idempotency_key, body.model_dump(),
                lambda: dict(zip(("document_id", "job_id"), create_url_source(conn, principal.company_id, body.url))),
            )
        return result
    except SourceError as exc:
        raise PublicAPIError(exc.status_code, exc.code, exc.message)


# --- events:webhook ---------------------------------------------------------


class WebhookEndpointRequest(BaseModel):
    url: str = Field(..., max_length=2000)
    events: list[str] = Field(default_factory=list, max_length=20)


@router.post("/webhooks")
async def register_webhook(body: WebhookEndpointRequest, principal: ApiKeyPrincipal = Depends(require_scope("events:webhook"))):
    secret = secrets.token_urlsafe(32)
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO webhook_endpoints (company_id, url, secret, events)
            VALUES (%s, %s, %s, %s)
            RETURNING id, url, events, created_at
            """,
            (principal.company_id, body.url, secret, body.events),
        ).fetchone()
    return {**dict(row), "id": str(row["id"]), "secret": secret}


@router.get("/webhooks")
async def list_webhooks(principal: ApiKeyPrincipal = Depends(require_scope("events:webhook"))):
    with connection() as conn:
        rows = conn.execute(
            "SELECT id, url, events, is_active, created_at FROM webhook_endpoints WHERE company_id = %s ORDER BY created_at DESC",
            (principal.company_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@router.delete("/webhooks/{webhook_id}")
async def delete_webhook(webhook_id: str, principal: ApiKeyPrincipal = Depends(require_scope("events:webhook"))):
    with connection() as conn:
        result = conn.execute(
            "DELETE FROM webhook_endpoints WHERE id = %s AND company_id = %s",
            (webhook_id, principal.company_id),
        )
    if result.rowcount == 0:
        raise PublicAPIError(404, "webhook_not_found", "Webhook endpoint not found.")
    return {"deleted": True}
