"""Shared types for the RAG v2 pipeline (launch/05-RAG-V2-SPEC.md §2).
Only what D3.4 (retrieve + rerank) needs today; the remaining stages
(guard/intent/rewrite/grade/generate/verify/postprocess) and the
pipeline.py entrypoint that wires them into a state machine are Day 4
(D4.1) -- not built yet, so nothing here is imported into the live chat
path. app/chat/pipeline.py (the current, proven single-shot pipeline)
is unchanged and still what serves real traffic.
"""
from dataclasses import dataclass


@dataclass
class Scope:
    company_id: str
    bot_id: str
    publication_id: str | None
    conversation_id: str
    is_preview: bool
    language_hint: str | None = None


@dataclass
class Passage:
    chunk_id: str
    document_id: str
    version_id: str
    title: str
    page: int | None
    heading: str | None
    text: str
    score_dense: float
    score_fts: float
    rrf: float
    score_rerank: float | None = None
