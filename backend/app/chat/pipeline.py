"""Shared chat pipeline for public visitor chat and owner draft preview
(docs/19 Phase 6, docs/16 "SSE transport").

Order of operations per turn (docs/03-TRD.md query pipeline):
  guard input -> idempotency replay check -> quota reserve -> persist user
  turn -> embed -> retrieve (Pinecone, filtered to the authorised source
  versions) -> validate against Postgres -> ground -> stream -> finalize.

Authorisation scope is ALWAYS derived server-side (the active publication's
source versions for visitors, the company's ready versions for owner
preview); nothing about scope is read from the request body.

SSE contract: events `meta`, `sources`, `delta`, `done`, `error`, each with
a monotonically increasing `seq`; `: heartbeat` comment lines while waiting
on the provider; a terminal `done` or `error` is always sent on a connected
stream. Client abort (cancellation / aclose) marks the assistant message
`interrupted`, keeps the partial text, and releases the quota reservation.
"""
import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator

from fastapi.responses import StreamingResponse
from psycopg.errors import UniqueViolation

from app.chat import llm, quota
from app.config import settings
from app.db import connection
from app.guardrails import classify_input, contains_sensitive_output
from app.jobs.runner import QuotaWaitError

log = logging.getLogger(__name__)

HEARTBEAT_SECONDS = 15.0
MAX_EVIDENCE_CHUNKS = 5
MAX_MESSAGE_CHARS = 4000
BLOCKED_OUTPUT_TEXT = "The response was blocked by the sensitive-data output guardrail."
SSE_HEADERS = {"Cache-Control": "no-cache, no-transform", "Connection": "keep-alive", "X-Accel-Buffering": "no"}


class ChatError(Exception):
    def __init__(self, status_code: int, code: str, message: str, retry_after_seconds: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retry_after_seconds = retry_after_seconds


@dataclass
class Scope:
    company_id: str
    bot_id: str
    conversation_id: str
    config: dict
    version_ids: list[str]
    is_preview: bool
    actor: str  # 'visitor' | 'owner'
    actor_id: str


@dataclass
class Turn:
    scope: Scope
    question: str = ""
    history: list[dict] = field(default_factory=list)
    user_message_id: str = ""
    assistant_message_id: str = ""
    generation_id: str = ""
    reservation_id: str = ""
    replay: dict | None = None  # completed assistant message to replay


# --- SSE helpers ----------------------------------------------------------


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def sse_response(generator: AsyncIterator[str]) -> StreamingResponse:
    return StreamingResponse(generator, media_type="text/event-stream", headers=SSE_HEADERS)


# --- Analytics ------------------------------------------------------------


def record_event(conn, scope: Scope, event_type: str, message_id: str | None = None, properties: dict | None = None) -> None:
    conn.execute(
        """
        INSERT INTO analytics_events (company_id, bot_id, conversation_id, message_id, event_type, properties)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        """,
        (scope.company_id, scope.bot_id, scope.conversation_id, message_id, event_type, json.dumps(properties or {})),
    )


# --- Scope resolution -----------------------------------------------------


def require_uuid(value: str, code: str = "conversation_not_found", message: str = "Conversation not found.") -> None:
    """Malformed ids are a 404 (same as 'not yours'), never a 500."""
    try:
        uuid.UUID(value)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ChatError(404, code, message) from exc


def visitor_scope(conn, visitor_session_id: str, conversation_id: str) -> Scope:
    require_uuid(conversation_id)
    row = conn.execute(
        """
        SELECT c.id, c.bot_id, b.company_id, b.active_publication_id
        FROM conversations c JOIN bots b ON b.id = c.bot_id
        WHERE c.id = %s AND c.visitor_session_id = %s AND NOT c.is_preview
        """,
        (conversation_id, visitor_session_id),
    ).fetchone()
    if not row:
        raise ChatError(404, "conversation_not_found", "Conversation not found.")
    if not row["active_publication_id"]:
        raise ChatError(404, "bot_unpublished", "This assistant is not currently published.")
    publication = conn.execute(
        "SELECT config_snapshot FROM publications WHERE id = %s", (row["active_publication_id"],)
    ).fetchone()
    versions = conn.execute(
        """
        SELECT ps.document_version_id AS id
        FROM publication_sources ps
        JOIN document_versions dv ON dv.id = ps.document_version_id
        JOIN documents d ON d.id = dv.document_id
        WHERE ps.publication_id = %s AND dv.status = 'ready' AND d.deleted_at IS NULL
        """,
        (row["active_publication_id"],),
    ).fetchall()
    return Scope(
        company_id=str(row["company_id"]),
        bot_id=str(row["bot_id"]),
        conversation_id=str(row["id"]),
        config=publication["config_snapshot"] or {},
        version_ids=[str(v["id"]) for v in versions],
        is_preview=False,
        actor="visitor",
        actor_id=visitor_session_id,
    )


def owner_preview_scope(conn, company_id: str, owner_user_id: str, conversation_id: str) -> Scope:
    require_uuid(conversation_id)
    row = conn.execute(
        """
        SELECT c.id, c.bot_id, b.draft_config
        FROM conversations c JOIN bots b ON b.id = c.bot_id
        WHERE c.id = %s AND b.company_id = %s AND c.is_preview
        """,
        (conversation_id, company_id),
    ).fetchone()
    if not row:
        raise ChatError(404, "conversation_not_found", "Preview conversation not found.")
    versions = conn.execute(
        """
        SELECT dv.id FROM documents d
        JOIN document_versions dv ON dv.id = d.active_version_id
        WHERE d.company_id = %s AND d.deleted_at IS NULL AND dv.status = 'ready'
        """,
        (company_id,),
    ).fetchall()
    return Scope(
        company_id=company_id,
        bot_id=str(row["bot_id"]),
        conversation_id=str(row["id"]),
        config=row["draft_config"] or {},
        version_ids=[str(v["id"]) for v in versions],
        is_preview=True,
        actor="owner",
        actor_id=owner_user_id,
    )


def create_preview_conversation(conn, company_id: str) -> str:
    bot = conn.execute("SELECT id FROM bots WHERE company_id = %s", (company_id,)).fetchone()
    if not bot:
        raise ChatError(404, "no_bot", "No bot found for this company.")
    row = conn.execute(
        "INSERT INTO conversations (bot_id, is_preview) VALUES (%s, true) RETURNING id", (bot["id"],)
    ).fetchone()
    return str(row["id"])


# --- Turn preparation -----------------------------------------------------


def _find_replay(conn, conversation_id: str, client_key: str) -> dict | None:
    user = conn.execute(
        "SELECT id, created_at FROM messages WHERE conversation_id = %s AND client_key = %s",
        (conversation_id, client_key),
    ).fetchone()
    if not user:
        return None
    assistant = conn.execute(
        """
        SELECT id, content, status, citations, generation_id FROM messages
        WHERE conversation_id = %s AND role = 'assistant' AND created_at >= %s
        ORDER BY created_at ASC LIMIT 1
        """,
        (conversation_id, user["created_at"]),
    ).fetchone()
    if assistant and assistant["status"] == "completed":
        return dict(assistant)
    raise ChatError(409, "request_in_progress", "A request with this Idempotency-Key is already in progress or did not complete. Use a new key to retry.")


def prepare_turn(scope: Scope, text: str, client_key: str | None) -> Turn:
    """Everything that must happen before any provider call. Raises
    ChatError (mapped to an HTTP error by the router) so a rejected turn
    never opens an SSE stream."""
    text = (text or "").strip()
    if not text or len(text) > MAX_MESSAGE_CHARS:
        raise ChatError(422, "invalid_message", f"Message must be 1-{MAX_MESSAGE_CHARS} characters.")
    if classify_input(text):
        raise ChatError(400, "input_blocked", "This message was blocked by input guardrails.")

    quota_error: quota.QuotaExceeded | None = None
    turn = Turn(scope=scope, question=text)
    with connection() as conn:
        if client_key:
            replay = _find_replay(conn, scope.conversation_id, client_key)
            if replay:
                turn.replay = replay
                return turn

        try:
            turn.reservation_id = quota.reserve(
                conn, scope.company_id, scope.conversation_id, llm.estimate_tokens(text) + llm.MAX_OUTPUT_TOKENS
            )
        except quota.QuotaExceeded as exc:
            quota_error = exc
            record_event(conn, scope, "quota_blocked", properties={"scope": exc.scope})

        if quota_error is None:
            history_rows = conn.execute(
                """
                SELECT role, content FROM messages
                WHERE conversation_id = %s AND status = 'completed'
                ORDER BY created_at DESC LIMIT 6
                """,
                (scope.conversation_id,),
            ).fetchall()
            turn.history = [{"role": r["role"], "content": r["content"]} for r in reversed(history_rows)]
            try:
                with conn.transaction():
                    user_row = conn.execute(
                        "INSERT INTO messages (conversation_id, role, content, status, client_key, created_at) VALUES (%s, 'user', %s, 'completed', %s, clock_timestamp()) RETURNING id",
                        (scope.conversation_id, text, client_key),
                    ).fetchone()
            except UniqueViolation:
                raise ChatError(409, "request_in_progress", "This Idempotency-Key is already being processed.")
            turn.user_message_id = str(user_row["id"])
            assistant_row = conn.execute(
                """
                INSERT INTO messages (conversation_id, role, content, status, generation_id, created_at)
                VALUES (%s, 'assistant', '', 'streaming', gen_random_uuid(), clock_timestamp()) RETURNING id, generation_id
                """,
                (scope.conversation_id,),
            ).fetchone()
            turn.assistant_message_id = str(assistant_row["id"])
            turn.generation_id = str(assistant_row["generation_id"])
            conn.execute("UPDATE conversations SET updated_at = now() WHERE id = %s", (scope.conversation_id,))
            record_event(conn, scope, "message_sent", message_id=turn.user_message_id, properties={"preview": scope.is_preview})

    if quota_error:
        raise ChatError(429, "quota_exhausted", "The daily free usage limit has been reached.", quota_error.retry_after_seconds)
    return turn


# --- Retrieval ------------------------------------------------------------


def _embed_query(text: str) -> list[float]:
    from app.providers.embeddings import embed_batch

    return embed_batch([text])[0]


def _vector_query(company_id: str, vector: list[float], version_ids: list[str]) -> list[dict]:
    from app.providers.vector_store import query_chunks

    return query_chunks(company_id, vector, version_ids, top_k=MAX_EVIDENCE_CHUNKS)


def retrieve(scope: Scope, question: str, history: list[dict]) -> list[dict]:
    """Returns authorised, Postgres-validated evidence passages. Pinecone
    hits are only candidates: each must still resolve to a ready, non-deleted
    chunk of an authorised version of THIS company before it is used."""
    if not scope.version_ids:
        return []
    prior_user = [m["content"] for m in history if m["role"] == "user"]
    query = (prior_user[-1][:500] + "\nFollow-up: " + question) if prior_user else question

    try:
        vector = _embed_query(query)
    except QuotaWaitError as exc:
        raise ChatError(429, "quota_exhausted", "Embedding quota exhausted.", exc.retry_after_seconds)
    except Exception as exc:  # noqa: BLE001 - provider adapters raise job-runner error types
        raise ChatError(503, "embedding_unavailable", "Search is temporarily unavailable.") from exc

    try:
        matches = _vector_query(scope.company_id, vector, scope.version_ids)
    except Exception as exc:  # noqa: BLE001
        raise ChatError(503, "retrieval_unavailable", "Search is temporarily unavailable.") from exc

    threshold = settings().min_relevance
    matches = [m for m in matches if m["score"] >= threshold]
    if not matches:
        return []
    score_by_id = {m["id"]: m["score"] for m in matches}

    with connection() as conn:
        rows = conn.execute(
            """
            SELECT c.vector_id, c.text, c.page, c.heading, d.id AS document_id, d.title
            FROM chunks c
            JOIN document_versions dv ON dv.id = c.version_id
            JOIN documents d ON d.id = dv.document_id
            WHERE c.vector_id = ANY(%s) AND dv.id = ANY(%s::uuid[])
              AND d.company_id = %s AND d.deleted_at IS NULL AND dv.status = 'ready'
            """,
            (list(score_by_id), scope.version_ids, scope.company_id),
        ).fetchall()
    rows = sorted(rows, key=lambda r: score_by_id[r["vector_id"]], reverse=True)[:MAX_EVIDENCE_CHUNKS]
    return [
        {
            "index": i + 1,
            "document_id": str(r["document_id"]),
            "title": r["title"],
            "page": r["page"],
            "heading": r["heading"],
            "text": r["text"] or "",
        }
        for i, r in enumerate(rows)
    ]


def public_sources(passages: list[dict]) -> list[dict]:
    return [
        {"index": p["index"], "document_id": p["document_id"], "title": p["title"], "page": p["page"], "excerpt": p["text"][:320]}
        for p in passages
    ]


def build_evidence(passages: list[dict]) -> str:
    return "\n\n".join(
        f"[{p['index']}] {p['title']}" + (f", page {p['page']}" if p["page"] else "") + f": {p['text']}" for p in passages
    )


# --- Finalisation ---------------------------------------------------------


def finalize_turn(turn: Turn, status: str, content: str, sources: list[dict], usage: dict, used_llm: bool, embedded: bool, error_code: str | None = None) -> None:
    scope = turn.scope
    with connection() as conn:
        conn.execute(
            "UPDATE messages SET content = %s, status = %s, citations = %s::jsonb, usage = %s::jsonb WHERE id = %s",
            (content, status, json.dumps(sources), json.dumps({**usage, "error_code": error_code}), turn.assistant_message_id),
        )
        if status == "completed" and used_llm:
            quota.commit(conn, scope.company_id, turn.reservation_id, usage.get("total_tokens_est", 0))
        else:
            quota.release(conn, turn.reservation_id)
        if embedded:
            quota.record_embedding(conn, scope.company_id)
        if status == "completed" and not sources:
            record_event(conn, scope, "answer_no_evidence", message_id=turn.assistant_message_id)
        conn.execute("UPDATE conversations SET updated_at = now() WHERE id = %s", (scope.conversation_id,))


# --- Streaming ------------------------------------------------------------


async def _with_heartbeat(agen) -> AsyncIterator[str | None]:
    """Yields provider chunks, or None every HEARTBEAT_SECONDS of silence
    without ever cancelling the underlying provider stream."""
    iterator = agen.__aiter__()
    task = None
    try:
        while True:
            task = asyncio.ensure_future(iterator.__anext__())
            while True:
                done, _ = await asyncio.wait({task}, timeout=HEARTBEAT_SECONDS)
                if done:
                    break
                yield None
            try:
                item = task.result()
            except StopAsyncIteration:
                return
            task = None
            yield item
    finally:
        if task is not None and not task.done():
            task.cancel()
        aclose = getattr(agen, "aclose", None)
        if aclose:
            try:
                await aclose()
            except Exception:  # noqa: BLE001
                pass


async def replay_stream(turn: Turn) -> AsyncIterator[str]:
    msg = turn.replay
    sources = (msg.get("citations") or []) if isinstance(msg.get("citations"), list) else []
    yield sse("meta", {"seq": 1, "conversation_id": turn.scope.conversation_id, "message_id": str(msg["id"]), "replayed": True})
    yield sse("sources", {"seq": 2, "sources": sources})
    yield sse("delta", {"seq": 3, "text": msg["content"]})
    yield sse("done", {"seq": 4, "message_id": str(msg["id"]), "replayed": True})


async def stream_turn(turn: Turn) -> AsyncIterator[str]:
    scope = turn.scope
    seq = 0

    def event(name: str, data: dict) -> str:
        nonlocal seq
        seq += 1
        return sse(name, {"seq": seq, **data})

    answer = ""
    sources: list[dict] = []
    used_llm = False
    embedded = False
    status = "interrupted"  # what a cancelled/aborted stream is recorded as
    error_code: str | None = None
    finalized = False
    prompt_tokens = 0

    def usage() -> dict:
        completion = llm.estimate_tokens(answer) if answer else 0
        return {"prompt_tokens_est": prompt_tokens, "completion_tokens_est": completion, "total_tokens_est": prompt_tokens + completion}

    try:
        yield event("meta", {"conversation_id": scope.conversation_id, "message_id": turn.assistant_message_id, "generation_id": turn.generation_id})

        failure: ChatError | llm.LLMError | None = None
        passages: list[dict] = []
        try:
            passages = await asyncio.to_thread(retrieve, scope, turn.question, turn.history)
            embedded = bool(scope.version_ids)
        except ChatError as exc:
            failure = exc

        if failure is None:
            sources = public_sources(passages)
            yield event("sources", {"sources": sources})

            if not passages:
                answer = scope.config.get("fallback_message") or "I couldn't find an answer to that in the available information."
                yield event("delta", {"text": answer})
                status = "completed"
            else:
                used_llm = True
                messages = llm.build_messages(scope.config, turn.question, build_evidence(passages), turn.history)
                prompt_tokens = llm.estimate_tokens(*(m["content"] for m in messages))
                try:
                    async for chunk in _with_heartbeat(llm.stream_completion(messages)):
                        if chunk is None:
                            yield ": heartbeat\n\n"
                            continue
                        answer += chunk
                        yield event("delta", {"text": chunk})
                    status = "completed"
                except llm.LLMError as exc:
                    failure = exc

        if failure is None and status == "completed" and contains_sensitive_output(answer):
            answer = BLOCKED_OUTPUT_TEXT
            failure = ChatError(200, "output_blocked", BLOCKED_OUTPUT_TEXT)

        if failure is not None:
            status = "failed"
            error_code = failure.code
            await asyncio.to_thread(finalize_turn, turn, status, answer, sources, usage(), used_llm, embedded, error_code)
            finalized = True
            payload = {"code": failure.code, "message": getattr(failure, "message", failure.code)}
            retry_after = getattr(failure, "retry_after_seconds", None)
            if retry_after:
                payload["retry_after_seconds"] = retry_after
            yield event("error", payload)
            return

        await asyncio.to_thread(finalize_turn, turn, "completed", answer, sources, usage(), used_llm, embedded)
        finalized = True
        yield event("done", {"message_id": turn.assistant_message_id, "usage": usage()})
    except asyncio.CancelledError:
        status = "interrupted"
        raise
    except GeneratorExit:
        status = "interrupted"
        raise
    except Exception as exc:  # noqa: BLE001 - never leave a connected stream without a terminal event
        log.exception("chat stream failed")
        status = "failed"
        error_code = "internal_error"
        if not finalized:
            try:
                await asyncio.to_thread(finalize_turn, turn, status, answer, sources, usage(), used_llm, embedded, error_code)
                finalized = True
            except Exception:  # noqa: BLE001
                log.exception("finalize after failure failed")
        yield event("error", {"code": "internal_error", "message": "Something went wrong."})
    finally:
        if not finalized:
            # Client abort / server shutdown: persist partial text as
            # 'interrupted' and free the reservation. Synchronous on purpose
            # so it still runs while the task is being cancelled.
            try:
                finalize_turn(turn, status, answer, sources, usage(), used_llm, embedded, error_code or "client_aborted")
            except Exception:  # noqa: BLE001
                log.exception("finalize on abort failed")
