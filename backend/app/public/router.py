"""Public visitor endpoints (docs/16-API-ROUTES.md "Visitor bootstrap and
chat (public)"). No owner session is accepted here: visitors authenticate
with a short-lived, bot-scoped visitor token from the bootstrap call, and a
visitor token is never accepted on any owner route (separate tables).

Bootstrap origin validation (bot domain allowlist) supplements the token
check; it is not proof of a human visitor (docs/06-API.md).
"""
import hashlib
import json
import secrets
from dataclasses import dataclass
from urllib.parse import urlparse

import asyncio

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, EmailStr, Field
from starlette.concurrency import run_in_threadpool

from app.auth.service import resolve_session
from app.chat import pipeline
from app.chat.pipeline import ChatError
from app.config import settings
from app.db import connection
from app.events.outbox import emit_event
from app.realtime.pubsub import conversation_channel
from app.realtime.router import _CONVERSATION_TOPICS, _seed_from_outbox, _stream, SSE_HEADERS
from app.security.rate_limit import RateLimited

router = APIRouter(prefix="/api/v1/public", tags=["public"])

VISITOR_TOKEN_TTL_MINUTES = 30
SESSION_RATE_LIMIT = 30  # bootstrap calls per IP per minute


def _error(status: int, code: str, message: str, headers: dict | None = None) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message}, headers=headers)


def _raise_chat(exc: ChatError):
    headers = {"Retry-After": str(exc.retry_after_seconds)} if exc.retry_after_seconds else None
    detail = {"code": exc.code, "message": exc.message}
    if exc.retry_after_seconds:
        detail["retry_after_seconds"] = exc.retry_after_seconds
    raise HTTPException(status_code=exc.status_code, detail=detail, headers=headers)


def _require_uuid(value: str, code: str, message: str) -> None:
    try:
        pipeline.require_uuid(value, code, message)
    except ChatError as exc:
        raise _error(404, exc.code, exc.message) from exc


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# --- Origin allowlist -------------------------------------------------------


def _origin_host(origin: str | None) -> str | None:
    if not origin:
        return None
    parsed = urlparse(origin if "://" in origin else f"//{origin}")
    return (parsed.hostname or "").lower() or None


def origin_allowed(allowed_domains: list[str], origin: str | None) -> bool:
    """No configured domains = open (owner has not restricted the bot yet).
    Once any domain is configured, the Origin header must match one
    exactly, or a `*.example.com` wildcard must match a subdomain."""
    if not allowed_domains:
        return True
    host = _origin_host(origin)
    if not host:
        return False
    for domain in allowed_domains:
        domain = domain.lower().strip()
        if domain.startswith("*."):
            if host.endswith(domain[1:]) and host != domain[2:]:
                return True
        elif host == domain:
            return True
    return False


def _check_origin(conn, bot_id: str, origin: str | None) -> None:
    rows = conn.execute("SELECT domain FROM bot_domains WHERE bot_id = %s", (bot_id,)).fetchall()
    if not origin_allowed([r["domain"] for r in rows], origin):
        raise _error(403, "origin_not_allowed", "This origin is not allowed to use this assistant.")




# --- Auth -------------------------------------------------------------------


@dataclass
class VisitorPrincipal:
    session_id: str
    bot_id: str
    company_id: str


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise _error(401, "unauthenticated", "Missing visitor token.")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise _error(401, "unauthenticated", "Missing visitor token.")
    return token


def _lookup_visitor(conn, token: str) -> VisitorPrincipal | None:
    row = conn.execute(
        """
        SELECT vs.id, vs.bot_id, b.company_id
        FROM visitor_sessions vs JOIN bots b ON b.id = vs.bot_id
        WHERE vs.session_token_hash = %s AND vs.expires_at > now()
        """,
        (hash_token(token),),
    ).fetchone()
    if not row:
        return None
    return VisitorPrincipal(session_id=str(row["id"]), bot_id=str(row["bot_id"]), company_id=str(row["company_id"]))


def get_visitor(authorization: str | None = Header(default=None)) -> VisitorPrincipal:
    token = _bearer(authorization)
    with connection() as conn:
        principal = _lookup_visitor(conn, token)
    if not principal:
        raise _error(401, "invalid_session", "Invalid or expired visitor token.")
    return principal


# --- Config + bootstrap -----------------------------------------------------


@router.get("/bots/{public_id}/config")
def get_public_bot_config(public_id: str, request: Request):
    with connection() as conn:
        bot = conn.execute(
            """
            SELECT b.id, p.config_snapshot
            FROM bots b JOIN publications p ON p.id = b.active_publication_id
            WHERE b.public_id = %s AND b.disabled_at IS NULL
            """,
            (public_id,),
        ).fetchone()
        if not bot:
            raise _error(404, "bot_not_found", "Assistant not found or not published.")
        _check_origin(conn, bot["id"], request.headers.get("origin"))
        lead_form = conn.execute(
            "SELECT 1 FROM lead_forms WHERE bot_id = %s AND is_active", (bot["id"],)
        ).fetchone()
    config = bot["config_snapshot"] or {}
    return {
        "name": config.get("name", "Assistant"),
        "branding": config.get("branding", {}),
        "greeting": config.get("greeting", ""),
        "suggestions": config.get("suggestions", []),
        "tone": config.get("tone", "helpful"),
        "language": config.get("language", "en"),
        "lead_capture_enabled": bool(lead_form),
    }


@router.post(
    "/bots/{public_id}/sessions",
    status_code=201,
    dependencies=[Depends(RateLimited(SESSION_RATE_LIMIT, 60, "visitor_bootstrap"))],
)
def create_visitor_session(public_id: str, request: Request):
    token = secrets.token_urlsafe(32)
    with connection() as conn:
        bot = conn.execute(
            "SELECT id, active_publication_id FROM bots WHERE public_id = %s AND disabled_at IS NULL", (public_id,)
        ).fetchone()
        if not bot or not bot["active_publication_id"]:
            raise _error(404, "bot_not_found", "Assistant not found or not published.")
        _check_origin(conn, bot["id"], request.headers.get("origin"))
        row = conn.execute(
            """
            INSERT INTO visitor_sessions (bot_id, session_token_hash, expires_at)
            VALUES (%s, %s, now() + make_interval(mins => %s)) RETURNING expires_at
            """,
            (bot["id"], hash_token(token), VISITOR_TOKEN_TTL_MINUTES),
        ).fetchone()
    return {"visitor_token": token, "expires_at": row["expires_at"].isoformat()}


# --- Conversations + chat ---------------------------------------------------


@router.post("/conversations", status_code=201)
def create_conversation(visitor: VisitorPrincipal = Depends(get_visitor)):
    with connection() as conn:
        bot = conn.execute("SELECT active_publication_id FROM bots WHERE id = %s", (visitor.bot_id,)).fetchone()
        if not bot or not bot["active_publication_id"]:
            raise _error(404, "bot_unpublished", "This assistant is not currently published.")
        row = conn.execute(
            "INSERT INTO conversations (bot_id, publication_id, visitor_session_id) VALUES (%s, %s, %s) RETURNING id",
            (visitor.bot_id, bot["active_publication_id"], visitor.session_id),
        ).fetchone()
        conversation_id = str(row["id"])
        conn.execute(
            "INSERT INTO analytics_events (company_id, bot_id, conversation_id, event_type) VALUES (%s, %s, %s, 'conversation_started')",
            (visitor.company_id, visitor.bot_id, conversation_id),
        )
        emit_event(
            conn,
            visitor.company_id,
            "conversation.started",
            {"conversation_id": conversation_id, "bot_id": visitor.bot_id},
            bot_id=visitor.bot_id,
        )
    return {"conversation_id": conversation_id}


@router.get("/conversations/{conversation_id}/stream")
async def conversation_state_stream(
    conversation_id: str,
    since: str | None = Query(default=None),
    visitor: VisitorPrincipal = Depends(get_visitor),
):
    """Sidecar SSE (ADR 005): pushes handoff/agent-joined state events for
    the life of the tab. Separate from the chat SSE in send_message, which
    only streams a single reply and closes."""
    def _check():
        with connection() as conn:
            pipeline.visitor_scope(conn, visitor.session_id, conversation_id)

    try:
        await run_in_threadpool(_check)
    except ChatError as exc:
        _raise_chat(exc)

    seed = await run_in_threadpool(_seed_from_outbox, visitor.company_id, since, _CONVERSATION_TOPICS, conversation_id)
    return StreamingResponse(_stream(conversation_channel(conversation_id), seed), media_type="text/event-stream", headers=SSE_HEADERS)


class MessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=pipeline.MAX_MESSAGE_CHARS)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=None,
    dependencies=[Depends(RateLimited(20, 60, "public_chat_message"))],
)
async def send_message(
    conversation_id: str,
    body: MessageRequest,
    visitor: VisitorPrincipal = Depends(get_visitor),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    """Streams the grounded answer as SSE. Scope (which sources may be
    searched) is derived from the bot's active publication, never from the
    request. Replaying an Idempotency-Key returns the stored answer."""
    def _prepare():
        with connection() as conn:
            scope = pipeline.visitor_scope(conn, visitor.session_id, conversation_id)
        return pipeline.prepare_turn(scope, body.text, idempotency_key)

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


# --- Lead capture (V1: skippable, post-hoc) ---------------------------------


class LeadRequest(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    email: EmailStr | None = None
    consent: bool


@router.post(
    "/conversations/{conversation_id}/lead",
    status_code=201,
    dependencies=[Depends(RateLimited(5, 60, "public_lead"))],
)
def submit_lead(conversation_id: str, body: LeadRequest, visitor: VisitorPrincipal = Depends(get_visitor)):
    _require_uuid(conversation_id, "conversation_not_found", "Conversation not found.")
    if body.consent is not True:
        raise _error(422, "consent_required", "Consent is required to submit contact details.")
    values = {k: v for k, v in {"name": body.name, "email": body.email}.items() if v}
    if not values:
        raise _error(422, "empty_lead", "Provide a name or an email, or skip the form.")

    with connection() as conn:
        conv = conn.execute(
            "SELECT id FROM conversations WHERE id = %s AND visitor_session_id = %s AND NOT is_preview",
            (conversation_id, visitor.session_id),
        ).fetchone()
        if not conv:
            raise _error(404, "conversation_not_found", "Conversation not found.")
        form = conn.execute(
            "SELECT id FROM lead_forms WHERE bot_id = %s AND is_active ORDER BY created_at ASC LIMIT 1", (visitor.bot_id,)
        ).fetchone()
        if not form:
            raise _error(404, "no_lead_form", "Lead capture is not enabled for this assistant.")
        required = conn.execute(
            "SELECT field_key FROM lead_form_fields WHERE lead_form_id = %s AND is_required", (form["id"],)
        ).fetchall()
        missing = [r["field_key"] for r in required if r["field_key"] not in values]
        if missing:
            raise HTTPException(
                status_code=422,
                detail={"code": "required_fields_missing", "message": "Required fields are missing.", "fields": missing},
            )
        row = conn.execute(
            """
            INSERT INTO leads (conversation_id, lead_form_id, "values", consent_at)
            VALUES (%s, %s, %s::jsonb, now())
            ON CONFLICT (conversation_id) DO NOTHING RETURNING id
            """,
            (conversation_id, form["id"], json.dumps(values)),
        ).fetchone()
        if not row:
            raise _error(409, "lead_already_submitted", "Contact details were already submitted for this conversation.")
        conn.execute(
            "INSERT INTO analytics_events (company_id, bot_id, conversation_id, event_type) VALUES (%s, %s, %s, 'lead_submitted')",
            (visitor.company_id, visitor.bot_id, conversation_id),
        )
        emit_event(
            conn,
            visitor.company_id,
            "lead.submitted",
            {"conversation_id": conversation_id, "lead_id": str(row["id"]), "values": values},
            bot_id=visitor.bot_id,
        )
    return {"status": "submitted"}


# --- Feedback ---------------------------------------------------------------


class FeedbackRequest(BaseModel):
    rating: int
    comment: str | None = Field(default=None, max_length=2000)


@router.post(
    "/messages/{message_id}/feedback",
    status_code=201,
    dependencies=[Depends(RateLimited(10, 60, "public_feedback"))],
)
def submit_feedback(message_id: str, body: FeedbackRequest, authorization: str | None = Header(default=None)):
    """Accepts a visitor token OR an owner session. The message must sit in
    the caller's own authorised scope; anything else is a 404 (never a 403
    that would confirm the message exists)."""
    token = _bearer(authorization)  # authenticate-before-anything: 401 outranks 404/422
    _require_uuid(message_id, "message_not_found", "Message not found.")
    if body.rating not in (-1, 1):
        raise _error(422, "invalid_rating", "Rating must be 1 (helpful) or -1 (not helpful).")

    with connection() as conn:
        visitor = _lookup_visitor(conn, token)
        if visitor:
            actor, actor_id, company_id, bot_id = "visitor", visitor.session_id, visitor.company_id, visitor.bot_id
            msg = conn.execute(
                """
                SELECT m.id, m.conversation_id FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                WHERE m.id = %s AND m.role = 'assistant' AND c.visitor_session_id = %s
                """,
                (message_id, visitor.session_id),
            ).fetchone()
        else:
            principal = resolve_session(conn, token)
            if not principal or not principal.company_id:
                raise _error(401, "invalid_session", "Invalid or expired token.")
            actor, actor_id, company_id = "owner", principal.user_id, principal.company_id
            msg = conn.execute(
                """
                SELECT m.id, m.conversation_id, c.bot_id FROM messages m
                JOIN conversations c ON c.id = m.conversation_id
                JOIN bots b ON b.id = c.bot_id
                WHERE m.id = %s AND m.role = 'assistant' AND b.company_id = %s
                """,
                (message_id, company_id),
            ).fetchone()
            bot_id = str(msg["bot_id"]) if msg else None
        if not msg:
            raise _error(404, "message_not_found", "Message not found.")

        conn.execute(
            """
            INSERT INTO feedback (message_id, actor, actor_id, rating, comment)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (message_id, actor, actor_id) DO UPDATE SET rating = EXCLUDED.rating, comment = EXCLUDED.comment
            """,
            (message_id, actor, actor_id, body.rating, body.comment),
        )
        conn.execute(
            """
            INSERT INTO analytics_events (company_id, bot_id, conversation_id, message_id, event_type, properties)
            VALUES (%s, %s, %s, %s, 'feedback_given', %s::jsonb)
            """,
            (company_id, bot_id, msg["conversation_id"], message_id, json.dumps({"rating": body.rating, "actor": actor})),
        )
        emit_event(
            conn,
            company_id,
            "feedback.given",
            {
                "conversation_id": str(msg["conversation_id"]),
                "message_id": message_id,
                "rating": body.rating,
                "comment": body.comment,
                "actor": actor,
            },
            bot_id=bot_id,
        )
    return {"status": "recorded"}
