"""RAG v2 pipeline orchestrator (launch/05-RAG-V2-SPEC.md §2-3).
State machine: guard → intent → rewrite → retrieve → rerank →
grade (loop) → generate → verify → postprocess.

Activated when settings().rag_engine == 'v2'.  The v1 pipeline in
app/chat/pipeline.py stays untouched and continues to serve traffic
when rag_engine == 'v1' (the default).
"""
import asyncio
import json
import logging
import time
from typing import AsyncIterator

from app.chat.pipeline import (
    ChatError,
    Scope as V1Scope,
    Turn,
    _with_heartbeat,
    finalize_turn,
    record_event,
    sse,
)
from app.chat.rag_v2.base import Passage, Scope
from app.chat.rag_v2.config import RagConfig
from app.chat.rag_v2.errors import InputBlocked, RagV2Error, RetrievalUnavailable
from app.chat.rag_v2.stages import generate, grade, guard, intent, postprocess, rerank, retrieve, rewrite, verify
from app.chat.rag_v2.trace import write_trace
from app.db import connection
from app.guardrails import contains_sensitive_output

log = logging.getLogger(__name__)

BLOCKED_OUTPUT_TEXT = "The response was blocked by the sensitive-data output guardrail."


def _scope_v2_from_v1(v1: V1Scope) -> Scope:
    return Scope(
        company_id=v1.company_id,
        bot_id=v1.bot_id,
        publication_id=None,
        conversation_id=v1.conversation_id,
        is_preview=v1.is_preview,
    )


async def stream_turn_v2(turn: Turn) -> AsyncIterator[str]:
    """Full v2 pipeline behind SSE, drop-in replacement for
    pipeline.stream_turn when rag_engine='v2'."""
    v1_scope = turn.scope
    scope = _scope_v2_from_v1(v1_scope)
    config = RagConfig.from_bot_config(v1_scope.config)

    seq = 0
    timings: dict[str, int] = {}
    answer = ""
    sources: list[dict] = []
    used_llm = False
    embedded = False
    status = "interrupted"
    error_code: str | None = None
    finalized = False
    abstained = False
    escalated = False
    intent_result = None
    rewritten_queries: list[str] = []
    retrieved_raw: list[Passage] = []
    reranked_passages: list[Passage] = []
    grade_iterations = 0
    verifier_result_dict: dict | None = None

    def event(name: str, data: dict) -> str:
        nonlocal seq
        seq += 1
        return sse(name, {"seq": seq, **data})

    t_start = time.monotonic()
    ttft_ms: int | None = None  # D8.2 analytics: time to first `delta` SSE event

    def mark_ttft() -> None:
        nonlocal ttft_ms
        if ttft_ms is None:
            ttft_ms = int((time.monotonic() - t_start) * 1000)

    def usage() -> dict:
        from app.chat import llm
        completion = llm.estimate_tokens(answer) if answer else 0
        prompt = llm.estimate_tokens(turn.question)
        return {
            "prompt_tokens_est": prompt, "completion_tokens_est": completion,
            "total_tokens_est": prompt + completion, "ttft_ms": ttft_ms,
        }

    try:
        yield event("meta", {
            "conversation_id": v1_scope.conversation_id,
            "message_id": turn.assistant_message_id,
            "generation_id": turn.generation_id,
            "engine": "v2",
        })

        failure: ChatError | RagV2Error | None = None

        # --- Guard ---
        t0 = time.monotonic()
        try:
            normalized = guard.guard_input(turn.question)
        except InputBlocked as exc:
            failure = ChatError(exc.http_status, exc.code, exc.message)
        timings["guard"] = int((time.monotonic() - t0) * 1000)

        if failure:
            raise failure

        # --- Intent ---
        t0 = time.monotonic()
        with connection() as conn:
            intent_result = await intent.classify_intent(conn, scope, normalized)
        timings["intent"] = int((time.monotonic() - t0) * 1000)
        scope.language_hint = intent_result.language
        escalated = intent_result.severity == "critical" or intent_result.intent == "emergency"

        # --- Rewrite ---
        t0 = time.monotonic()
        rewritten_queries = await rewrite.rewrite_query(normalized, turn.history)
        timings["rewrite"] = int((time.monotonic() - t0) * 1000)

        # --- Retrieve (synchronous, runs in threadpool) ---
        t0 = time.monotonic()
        try:
            all_passages: list[Passage] = []
            for q in rewritten_queries:
                passages = await asyncio.to_thread(
                    lambda qq: _retrieve_sync(scope, qq), q
                )
                all_passages.extend(passages)
            seen_ids: set[str] = set()
            retrieved_raw = []
            for p in all_passages:
                if p.chunk_id not in seen_ids:
                    seen_ids.add(p.chunk_id)
                    retrieved_raw.append(p)
            embedded = True
        except Exception as exc:
            log.exception("v2 retrieval failed")
            failure = ChatError(503, "retrieval_unavailable", "Search is temporarily unavailable.")
        timings["retrieve"] = int((time.monotonic() - t0) * 1000)

        if failure:
            raise failure

        # --- Rerank ---
        t0 = time.monotonic()
        try:
            reranked_passages = await asyncio.to_thread(
                rerank.rerank, " ".join(rewritten_queries), retrieved_raw, config.rerank_top_k
            )
            if config.min_rerank_score > 0:
                reranked_passages = [p for p in reranked_passages if (p.score_rerank or 0) >= config.min_rerank_score]
        except Exception:
            log.warning("rerank fell through, using raw retrieval order")
            reranked_passages = retrieved_raw[:config.rerank_top_k]
        timings["rerank"] = int((time.monotonic() - t0) * 1000)

        sources = _public_sources(reranked_passages)
        yield event("sources", {"sources": sources})

        if not reranked_passages:
            answer = config.abstention_text
            mark_ttft()
            yield event("delta", {"text": answer})
            status = "completed"
            abstained = True
        else:
            # --- Grade loop ---
            t0 = time.monotonic()
            current_passages = reranked_passages
            current_query = " ".join(rewritten_queries)
            for iteration in range(config.max_loop_iterations):
                grade_iterations = iteration + 1
                grade_result = await grade.grade_sufficiency(current_query, current_passages)
                if grade_result.sufficient:
                    break
                if grade_result.suggest_subquery and iteration < config.max_loop_iterations - 1:
                    try:
                        extra = await asyncio.to_thread(
                            lambda qq: _retrieve_sync(scope, qq), grade_result.suggest_subquery
                        )
                        extra_reranked = await asyncio.to_thread(
                            rerank.rerank, grade_result.suggest_subquery, extra, config.rerank_top_k
                        )
                        existing_ids = {p.chunk_id for p in current_passages}
                        for p in extra_reranked:
                            if p.chunk_id not in existing_ids:
                                current_passages.append(p)
                                existing_ids.add(p.chunk_id)
                    except Exception:
                        log.warning("grade loop retrieval/rerank failed, breaking")
                        break
                else:
                    break
            reranked_passages = current_passages
            timings["grade"] = int((time.monotonic() - t0) * 1000)

            # --- Generate ---
            t0 = time.monotonic()
            used_llm = True
            messages = generate.build_messages(
                v1_scope.config, normalized, reranked_passages, turn.history,
                intent_result.language,
            )
            try:
                async for chunk in _with_heartbeat(generate.generate(messages, language=intent_result.language)):
                    if chunk is None:
                        yield ": heartbeat\n\n"
                        continue
                    answer += chunk
                    mark_ttft()
                    yield event("delta", {"text": chunk})
            except Exception as exc:
                log.exception("v2 generation failed")
                failure = ChatError(503, "llm_provider_error", "The assistant is temporarily unavailable.")
            timings["generate"] = int((time.monotonic() - t0) * 1000)

            if failure:
                raise failure

            # --- Verify ---
            if config.verifier_enabled and answer:
                t0 = time.monotonic()
                vr = await verify.verify_faithfulness(answer, reranked_passages)
                if not vr.faithful:
                    regen_messages = list(messages)
                    regen_messages.append({"role": "assistant", "content": answer})
                    regen_messages.append({
                        "role": "user",
                        "content": (
                            "The verifier flagged these unsupported claims: "
                            + "; ".join(vr.unsupported_claims)
                            + ". Please regenerate your answer, citing only what the evidence supports."
                        ),
                    })
                    regen_answer = ""
                    try:
                        async for chunk in generate.generate(regen_messages, language=intent_result.language):
                            regen_answer += chunk
                    except Exception:
                        log.warning("verify regen failed, keeping original answer")

                    if regen_answer:
                        vr2 = await verify.verify_faithfulness(regen_answer, reranked_passages)
                        if vr2.faithful:
                            answer = regen_answer
                            verifier_result_dict = {"faithful": True, "retried": True}
                        else:
                            answer = config.abstention_text
                            abstained = True
                            verifier_result_dict = {"faithful": False, "retried": True, "abstained": True}
                    else:
                        verifier_result_dict = {"faithful": False, "retried": False, "regen_failed": True}
                else:
                    verifier_result_dict = {"faithful": True}
                timings["verify"] = int((time.monotonic() - t0) * 1000)

            # --- Postprocess ---
            t0 = time.monotonic()
            if contains_sensitive_output(answer):
                answer = BLOCKED_OUTPUT_TEXT
            answer = postprocess.postprocess(answer, pii_redaction=config.pii_redaction)
            timings["postprocess"] = int((time.monotonic() - t0) * 1000)

            status = "completed"

        # --- Finalize ---
        await asyncio.to_thread(
            finalize_turn, turn, status, answer, sources, usage(), used_llm, embedded
        )
        finalized = True

        # --- Follow-ups ---
        follow_ups: list[str] = []
        if status == "completed" and not abstained and config.follow_ups_count > 0 and reranked_passages:
            evidence_summary = "\n".join(f"[{i+1}] {p.title}: {p.text[:200]}" for i, p in enumerate(reranked_passages[:3]))
            follow_ups = await postprocess.suggest_follow_ups(answer, evidence_summary, config.follow_ups_count)

        yield event("done", {
            "message_id": turn.assistant_message_id,
            "usage": usage(),
            "follow_ups": follow_ups,
        })

    except ChatError as exc:
        status = "failed"
        error_code = exc.code
        if not finalized:
            await asyncio.to_thread(
                finalize_turn, turn, status, answer, sources, usage(), used_llm, embedded, error_code
            )
            finalized = True
        payload = {"code": exc.code, "message": exc.message}
        if exc.retry_after_seconds:
            payload["retry_after_seconds"] = exc.retry_after_seconds
        yield event("error", payload)
    except asyncio.CancelledError:
        status = "interrupted"
        raise
    except GeneratorExit:
        status = "interrupted"
        raise
    except Exception:
        log.exception("v2 pipeline failed")
        status = "failed"
        error_code = "internal_error"
        if not finalized:
            try:
                await asyncio.to_thread(
                    finalize_turn, turn, status, answer, sources, usage(), used_llm, embedded, error_code
                )
                finalized = True
            except Exception:
                log.exception("finalize after failure failed")
        yield event("error", {"code": "internal_error", "message": "Something went wrong."})
    finally:
        latency_total = int((time.monotonic() - t_start) * 1000)
        if not finalized:
            try:
                finalize_turn(turn, status, answer, sources, usage(), used_llm, embedded, error_code or "client_aborted")
            except Exception:
                log.exception("finalize on abort failed")
        # Write trace (best-effort, never blocks the response)
        try:
            with connection() as conn:
                write_trace(
                    conn,
                    company_id=v1_scope.company_id,
                    conversation_id=v1_scope.conversation_id,
                    message_id=turn.assistant_message_id,
                    intent=intent_result.intent if intent_result else None,
                    severity=intent_result.severity if intent_result else None,
                    language=intent_result.language if intent_result else None,
                    rewritten_queries=rewritten_queries,
                    retrieved=[{"chunk_id": p.chunk_id, "score_dense": p.score_dense, "score_fts": p.score_fts, "rrf": p.rrf} for p in retrieved_raw],
                    reranked=[{"chunk_id": p.chunk_id, "score": p.score_rerank} for p in reranked_passages],
                    grade_iterations=grade_iterations,
                    verifier_result=verifier_result_dict,
                    latency_ms_total=latency_total,
                    latency_ms_per_stage=timings,
                    abstained=abstained,
                    escalated=escalated,
                )
        except Exception:
            log.exception("failed to write rag_trace")


def _retrieve_sync(scope: Scope, query_text: str) -> list[Passage]:
    with connection() as conn:
        return retrieve.retrieve(conn, scope, query_text)


def _public_sources(passages: list[Passage]) -> list[dict]:
    return [
        {
            "index": i + 1,
            "document_id": p.document_id,
            "title": p.title,
            "page": p.page,
            "excerpt": p.text[:320],
        }
        for i, p in enumerate(passages)
    ]
