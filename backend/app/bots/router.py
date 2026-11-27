"""Owner bot routes: draft config, publish, lead form, domains, embed/export,
draft preview chat and conversation history (docs/16-API-ROUTES.md)."""
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app.audit.service import audit_request_context, write_audit_event
from app.auth.service import SessionPrincipal
from app.bots import history, service
from app.bots.service import BotError
from app.chat import pipeline
from app.chat.pipeline import ChatError
from app.config import settings
from app.db import connection
from app.deps import get_verified_principal
from app.idempotency import run_idempotent

router = APIRouter(prefix="/api/v1", tags=["bot"])


def _raise(exc: BotError):
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def _raise_chat(exc: ChatError):
    headers = {"Retry-After": str(exc.retry_after_seconds)} if exc.retry_after_seconds else None
    detail = {"code": exc.code, "message": exc.message}
    if exc.retry_after_seconds:
        detail["retry_after_seconds"] = exc.retry_after_seconds
    raise HTTPException(status_code=exc.status_code, detail=detail, headers=headers)


def _require_company(principal: SessionPrincipal) -> str:
    if not principal.company_id:
        raise HTTPException(status_code=404, detail={"code": "no_company", "message": "No company found."})
    return principal.company_id


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-ID") or str(uuid.uuid4())


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError):
        return False


# --- Draft config -----------------------------------------------------------


@router.get("/bot")
def get_bot(principal: SessionPrincipal = Depends(get_verified_principal)):
    """Auto-provisions the company's bot on first access (same lazy-create
    semantics as every source-creation path) instead of 404ing -- a brand
    new company that hasn't added a source yet still needs a bot row to
    render Onboarding/Chatbot/Actions, which all fetch this first."""
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            service.get_or_create_bot_for_company(conn, company_id)
            bot = service.get_bot(conn, company_id)
    except BotError as exc:
        _raise(exc)
    return {
        "id": str(bot["id"]),
        "public_id": bot["public_id"],
        "draft_config": bot["draft_config"],
        "draft_revision": bot["draft_revision"],
        "active_publication_id": str(bot["active_publication_id"]) if bot["active_publication_id"] else None,
    }


class BotPatchRequest(BaseModel):
    draft_revision: int
    config_patch: dict = Field(default_factory=dict)


@router.patch("/bot")
def patch_bot(body: BotPatchRequest, request: Request, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            with audit_request_context(_request_id(request), company_id, "owner", principal.user_id):
                new_revision = service.update_draft_config(conn, company_id, body.draft_revision, body.config_patch)
                write_audit_event(conn, "update_draft_config", "bot", target_id=None, safe_metadata={"revision": new_revision})
    except BotError as exc:
        _raise(exc)
    return {"draft_revision": new_revision}


# --- Publish ----------------------------------------------------------------


class PublishRequest(BaseModel):
    selected_document_version_ids: list[str] = Field(min_length=1, max_length=200)


@router.post("/bot/publish", status_code=201)
def publish_bot(
    body: PublishRequest,
    request: Request,
    response: Response,
    principal: SessionPrincipal = Depends(get_verified_principal),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    company_id = _require_company(principal)
    if not all(_is_uuid(v) for v in body.selected_document_version_ids):
        raise HTTPException(status_code=422, detail={"code": "invalid_version_id", "message": "Source version ids must be UUIDs."})
    ids = sorted(set(body.selected_document_version_ids))
    try:
        with connection() as conn:
            with audit_request_context(_request_id(request), company_id, "owner", principal.user_id):

                def _publish() -> dict:
                    result = service.publish_bot(conn, company_id, ids)
                    write_audit_event(
                        conn, "publish", "publication", target_id=result["publication_id"],
                        safe_metadata={"version": result["version"], "source_count": len(ids)},
                    )
                    return result

                result, replayed = run_idempotent(conn, company_id, "bot.publish", idempotency_key, ids, _publish, 201)
    except BotError as exc:
        _raise(exc)
    if replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return result


@router.post("/bot/unpublish")
def unpublish_bot(request: Request, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            with audit_request_context(_request_id(request), company_id, "owner", principal.user_id):
                service.unpublish_bot(conn, company_id)
                write_audit_event(conn, "unpublish", "bot", target_id=None, safe_metadata={})
    except BotError as exc:
        _raise(exc)
    return {"status": "unpublished"}


# --- Lead form --------------------------------------------------------------


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
    try:
        with connection() as conn:
            with audit_request_context(_request_id(request), company_id, "owner", principal.user_id):
                service.update_lead_form_field_required(conn, company_id, field_key, body.is_required)
                write_audit_event(conn, "update_lead_form_field", "lead_form", target_id=None, safe_metadata={"field_key": field_key, "is_required": body.is_required})
    except BotError as exc:
        _raise(exc)
    return {"status": "updated"}


# --- Domains / embed / export -----------------------------------------------


class DomainsRequest(BaseModel):
    allowed_domains: list[str] = Field(max_length=history.MAX_DOMAINS)


@router.get("/bot/domains")
def get_domains(principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    with connection() as conn:
        return {"allowed_domains": history.get_domains(conn, company_id)}


@router.put("/bot/domains")
def put_domains(body: DomainsRequest, request: Request, principal: SessionPrincipal = Depends(get_verified_principal)):
    """Replaces the bot's allowed-origin list. An empty list means "no
    restriction" (the owner has not locked the widget to specific sites)."""
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            with audit_request_context(_request_id(request), company_id, "owner", principal.user_id):
                domains = history.replace_domains(conn, company_id, body.allowed_domains)
                write_audit_event(conn, "update_domains", "bot", target_id=None, safe_metadata={"count": len(domains)})
    except BotError as exc:
        _raise(exc)
    return {"allowed_domains": domains}


@router.get("/bot/embed")
def get_embed(principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            bot = service.get_bot(conn, company_id)
    except BotError as exc:
        _raise(exc)
    return history.embed_snippets(bot["public_id"])


def _download(payload: dict, filename: str) -> Response:
    return Response(
        content=history.export_json_bytes(payload),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/bot/export")
def export_bot(principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            payload = history.bot_export(conn, company_id)
    except BotError as exc:
        _raise(exc)
    return _download(payload, "bot-export.json")


# --- Owner draft preview ----------------------------------------------------


@router.post("/bot/preview/conversations", status_code=201)
def create_preview_conversation(principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            conversation_id = pipeline.create_preview_conversation(conn, company_id)
    except ChatError as exc:
        _raise_chat(exc)
    return {"conversation_id": conversation_id}


class PreviewChatRequest(BaseModel):
    conversation_id: str
    message: str = Field(min_length=1, max_length=pipeline.MAX_MESSAGE_CHARS)


@router.post("/bot/preview/chat", response_model=None)
async def preview_chat(
    body: PreviewChatRequest,
    principal: SessionPrincipal = Depends(get_verified_principal),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Same pipeline as public chat, but scoped to the owner's own ready
    sources and DRAFT config (docs/16: "Authenticated draft scope")."""
    company_id = _require_company(principal)
    if not _is_uuid(body.conversation_id):
        raise HTTPException(status_code=404, detail={"code": "conversation_not_found", "message": "Preview conversation not found."})
    def _prepare():
        with connection() as conn:
            scope = pipeline.owner_preview_scope(conn, company_id, principal.user_id, body.conversation_id)
        return pipeline.prepare_turn(scope, body.message, idempotency_key)

    try:
        turn = await run_in_threadpool(_prepare)
    except ChatError as exc:
        _raise_chat(exc)
    if turn.replay:
        return pipeline.sse_response(pipeline.replay_stream(turn))
    if settings().rag_engine == "v2":
        from app.chat.rag_v2.pipeline import stream_turn_v2
        return pipeline.sse_response(stream_turn_v2(turn))
    return pipeline.sse_response(pipeline.stream_turn(turn))


# --- Conversation history ---------------------------------------------------


@router.get("/conversations")
def list_conversations(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    status: str | None = None,
    has_feedback: bool | None = None,
    tags: str | None = Query(default=None, description="Comma-separated; conversation matches if it has ANY of these tags"),
    cursor: str | None = None,
    limit: int = Query(default=history.DEFAULT_PAGE_SIZE, ge=1, le=history.MAX_PAGE_SIZE),
    principal: SessionPrincipal = Depends(get_verified_principal),
):
    company_id = _require_company(principal)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    try:
        with connection() as conn:
            return history.list_conversations(conn, company_id, date_from, date_to, status, has_feedback, tag_list, cursor, limit)
    except BotError as exc:
        _raise(exc)


@router.get("/conversations/export.csv")
def export_conversations_csv(
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    status: str | None = None,
    has_feedback: bool | None = None,
    tags: str | None = Query(default=None),
    principal: SessionPrincipal = Depends(get_verified_principal),
):
    company_id = _require_company(principal)
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    try:
        with connection() as conn:
            csv_text = history.export_conversations_csv(conn, company_id, date_from, date_to, status, has_feedback, tag_list)
    except BotError as exc:
        _raise(exc)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="conversations.csv"'},
    )


class TagsRequest(BaseModel):
    tags: list[str] = Field(default_factory=list, max_length=50)


@router.put("/conversations/{conversation_id}/tags")
def set_conversation_tags(conversation_id: str, body: TagsRequest, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            tags = history.set_conversation_tags(conn, company_id, conversation_id, body.tags)
    except BotError as exc:
        _raise(exc)
    return {"tags": tags}


@router.get("/conversations/{conversation_id}")
def get_conversation(conversation_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            return history.get_conversation_detail(conn, company_id, conversation_id)
    except BotError as exc:
        _raise(exc)


@router.delete("/conversations/{conversation_id}", status_code=202)
def delete_conversation(conversation_id: str, request: Request, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            with audit_request_context(_request_id(request), company_id, "owner", principal.user_id):
                history.delete_conversation(conn, company_id, conversation_id)
                write_audit_event(conn, "delete", "conversation", target_id=conversation_id, safe_metadata={})
    except BotError as exc:
        _raise(exc)
    return {"status": "deleted"}


@router.get("/conversations/{conversation_id}/export")
def export_conversation(conversation_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            payload = history.get_conversation_detail(conn, company_id, conversation_id)
    except BotError as exc:
        _raise(exc)
    return _download(payload, f"conversation-{conversation_id}.json")


# --- Tenant data deletion ---------------------------------------------------


# NOTE: `DELETE /api/v1/account` was removed on Day 1 as part of the
# docs/16 route audit (see launch/00-BUILD-HEALTH.md §5). It duplicated
# `DELETE /api/v1/me` in `app/profile_router.py`, which is the canonical
# endpoint per docs/16-API-ROUTES.md. The cleanup logic
# (`app/bots/history.purge_company_data`) still ships; it is now called
# only from the `company_cleanup` job queued by `DELETE /me`.
