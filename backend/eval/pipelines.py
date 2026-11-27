"""Thin wrappers that run the current product's retrieval + generation in
Day-1 offline mode. No network calls, no real providers.

The "fake retriever" does deterministic keyword overlap against the corpus
so Day-1 baseline numbers are repeatable. On Day 3 we swap in the real
retrieval via Pinecone / pgvector hybrid.

The "fake generator" produces a templated answer that quotes the top
retrieved chunk and emits a safety phrase for emergency cases. This is
honest on Day 1 — the goal here is to prove the harness itself works,
not to pretend the LLM is live.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Iterable

from .schema import GoldenCase, StageTiming, TurnRun


CORPUS_ROOT = Path(__file__).parent / "corpora"

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(text) if len(m.group(0)) > 2}


def _load_corpus(name: str) -> list[dict]:
    path = CORPUS_ROOT / f"{name}.jsonl"
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def retrieve_fake(question: str, corpus: list[dict], top_k: int = 5) -> list[dict]:
    q_tokens = _tokens(question)
    scored: list[tuple[float, dict]] = []
    for row in corpus:
        c_tokens = _tokens(row["title"] + " " + row["text"])
        overlap = len(q_tokens & c_tokens)
        if overlap == 0:
            continue
        # Jaccard-ish rank
        score = overlap / max(1, len(q_tokens | c_tokens))
        scored.append((score, row))
    scored.sort(key=lambda s: s[0], reverse=True)
    return [r for _, r in scored[:top_k]]


SAFETY_KEYWORDS = ("suicide", "harm myself", "hurt myself", "kill myself", "unconscious", "fire", "bleeding", "poison", "overdose", "911", "988")
INJECTION_KEYWORDS = ("ignore previous", "reveal your", "system prompt", "pretend you", "bypass", "dump all", "api keys", "passwords")


def _is_emergency(question: str) -> bool:
    ql = question.lower()
    return any(k in ql for k in SAFETY_KEYWORDS)


def _is_injection(question: str) -> bool:
    ql = question.lower()
    return any(k in ql for k in INJECTION_KEYWORDS)


def generate_fake(question: str, passages: list[dict]) -> tuple[str, str]:
    """Returns (answer, status)."""
    if _is_emergency(question):
        ql = question.lower()
        line = "If you or someone else is in immediate danger, please call 911 right now."
        if any(k in ql for k in ("myself", "suicide", "crisis")):
            line += " For mental-health crises, call or text 988 (US Suicide & Crisis Lifeline)."
        return line + " I'm also notifying a human from the team.", "completed"
    if _is_injection(question):
        return "I can't share that information.", "abstained"
    if not passages:
        return "I couldn't find an answer to that in the available information.", "abstained"
    top = passages[0]
    return f"{top['text']} [1]", "completed"


def run_v1(case: GoldenCase, corpus: list[dict], top_k: int = 5) -> TurnRun:
    """Mirror of the current product's single-shot pipeline (embed → top-K
    → generate), using fake providers so Day-1 eval runs offline."""
    t0 = time.perf_counter()
    passages = retrieve_fake(case.question, corpus, top_k=top_k)
    t_retrieve = (time.perf_counter() - t0) * 1000.0
    t1 = time.perf_counter()
    answer, status = generate_fake(case.question, passages)
    t_gen = (time.perf_counter() - t1) * 1000.0
    total = (time.perf_counter() - t0) * 1000.0
    retrieved_ids = [p["chunk_id"] for p in passages]
    cited_ids = retrieved_ids[:1] if status == "completed" and passages else []
    return TurnRun(
        case_id=case.id,
        config="baseline_v1",
        status=status,  # type: ignore[arg-type]
        answer=answer,
        retrieved_ids=retrieved_ids,
        reranked_ids=retrieved_ids,  # v1 has no rerank step
        cited_ids=cited_ids,
        ttft_ms=t_retrieve + t_gen,  # fake: all tokens arrive at once
        total_ms=total,
        tokens_in=len(case.question.split()),
        tokens_out=len(answer.split()),
        provider="fake",
        model="fake-v1",
        stage_timings=[StageTiming("retrieve", t_retrieve), StageTiming("generate", t_gen)],
    )
