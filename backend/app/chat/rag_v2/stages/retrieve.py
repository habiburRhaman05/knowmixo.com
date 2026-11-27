"""Hybrid retrieval: dense (pgvector) + FTS, fused with Reciprocal Rank
Fusion in one SQL query (D3.4, ADR 001, launch/05-RAG-V2-SPEC.md §3.4).

Metadata filters (company_id, version_id, language) are applied INSIDE
each of the `dense` and `fts` CTEs separately, never after the UNION --
applying them post-union would let a passage that only matches one
branch's filter leak through via the other branch's unfiltered row
(ADR 001's own callout: "subtle correctness issue").

company_id is bound directly as a query parameter rather than read via
`current_setting('app.company_id')` (ADR 001's reference snippet) --
the live app's pool still runs on the RLS-bypass role (migration 0011's
documented, deliberate deferral), so that session variable isn't
guaranteed to be set yet. Binding it explicitly keeps this query
correct today AND after the eventual RLS cutover (RLS would then just
be a second, redundant guarantee, never the only one).

The FTS half queries each row with `chunks_language_to_tsconfig(c.language)`
(migration 0016) -- the SAME per-chunk config the chunks_tsvector_update
trigger used to build that row's stored tsvector. An earlier version of
this query hardcoded 'simple' on the query side while the stored
tsvector was built with a stemmed config (e.g. 'english'); since
'english' stems "policy" to "polici" and 'simple' does not, the two
sides' lexemes often never overlapped and FTS silently matched almost
nothing for ordinary English queries. Caught by
test/api/test_hybrid_retrieval.py before this ever reached a real
request -- see migration 0016's docstring.
"""
from app.chat.rag_v2.base import Passage, Scope
from app.providers.embeddings import embed_batch

RRF_K = 60
CANDIDATES_PER_BRANCH = 30


def retrieve(conn, scope: Scope, query_text: str, top_n: int = CANDIDATES_PER_BRANCH) -> list[Passage]:
    """Returns up to `top_n` Passage candidates ordered by fused RRF
    score, before rerank. Empty if the scope has no authorised versions."""
    version_ids = _version_ids_for_scope(conn, scope)
    return _retrieve(conn, scope.company_id, version_ids, query_text, scope.language_hint, top_n)


def _version_ids_for_scope(conn, scope: Scope) -> list[str]:
    """Mirrors app/chat/pipeline.py's existing visitor_scope/owner_preview_scope
    version resolution, kept here so retrieve() is callable standalone in
    tests without duplicating that query at every call site once Day 4's
    pipeline.py wires this stage in for real."""
    if scope.is_preview:
        rows = conn.execute(
            """
            SELECT dv.id FROM documents d
            JOIN document_versions dv ON dv.id = d.active_version_id
            WHERE d.company_id = %s AND d.deleted_at IS NULL AND d.disabled_at IS NULL AND dv.status = 'ready'
            """,
            (scope.company_id,),
        ).fetchall()
    elif scope.publication_id:
        rows = conn.execute(
            """
            SELECT ps.document_version_id AS id
            FROM publication_sources ps
            JOIN document_versions dv ON dv.id = ps.document_version_id
            JOIN documents d ON d.id = dv.document_id
            WHERE ps.publication_id = %s AND dv.status = 'ready' AND d.deleted_at IS NULL AND d.disabled_at IS NULL
            """,
            (scope.publication_id,),
        ).fetchall()
    else:
        rows = []
    return [str(r["id"]) for r in rows]


def retrieve_with_version_ids(
    conn, company_id: str, version_ids: list[str], query_text: str, language_hint: str | None = None, top_n: int = CANDIDATES_PER_BRANCH
) -> list[Passage]:
    """Same as retrieve(), for callers (tests, and Day 4's pipeline once
    it owns scope resolution itself) that already have `version_ids`."""
    return _retrieve(conn, company_id, version_ids, query_text, language_hint, top_n)


def _retrieve(
    conn, company_id: str, version_ids: list[str], query_text: str, language_hint: str | None, top_n: int
) -> list[Passage]:
    if not version_ids:
        return []

    vector = embed_batch([query_text])[0]

    rows = conn.execute(
        """
        WITH dense AS (
            SELECT c.id,
                   1 - (c.embedding <=> %(vector)s::vector) AS score
            FROM chunks c
            WHERE c.company_id = %(company_id)s
              AND c.version_id = ANY(%(version_ids)s::uuid[])
              AND c.embedding IS NOT NULL
              AND (%(language)s::text IS NULL OR c.language = %(language)s)
            ORDER BY c.embedding <=> %(vector)s::vector
            LIMIT %(per_branch)s
        ),
        fts AS (
            SELECT c.id,
                   ts_rank_cd(c.tsvector, plainto_tsquery(chunks_language_to_tsconfig(c.language), %(query_text)s)) AS score
            FROM chunks c
            WHERE c.company_id = %(company_id)s
              AND c.version_id = ANY(%(version_ids)s::uuid[])
              AND c.tsvector @@ plainto_tsquery(chunks_language_to_tsconfig(c.language), %(query_text)s)
              AND (%(language)s::text IS NULL OR c.language = %(language)s)
            ORDER BY score DESC
            LIMIT %(per_branch)s
        ),
        ranked AS (
            SELECT id, score AS score_dense, 0.0 AS score_fts,
                   1.0 / (%(rrf_k)s + row_number() OVER (ORDER BY score DESC)) AS rrf_score
            FROM dense
            UNION ALL
            SELECT id, 0.0 AS score_dense, score AS score_fts,
                   1.0 / (%(rrf_k)s + row_number() OVER (ORDER BY score DESC)) AS rrf_score
            FROM fts
        ),
        fused AS (
            SELECT id,
                   SUM(rrf_score) AS rrf,
                   MAX(score_dense) AS score_dense,
                   MAX(score_fts) AS score_fts
            FROM ranked
            GROUP BY id
        )
        SELECT
            c.id AS chunk_id, c.version_id, c.page, c.heading, c.text,
            d.id AS document_id, d.title,
            fused.rrf, fused.score_dense, fused.score_fts
        FROM fused
        JOIN chunks c ON c.id = fused.id
        JOIN document_versions dv ON dv.id = c.version_id
        JOIN documents d ON d.id = dv.document_id
        ORDER BY fused.rrf DESC
        LIMIT %(top_n)s
        """,
        {
            "vector": vector,
            "company_id": company_id,
            "version_ids": version_ids,
            "language": language_hint,
            "query_text": query_text,
            "per_branch": CANDIDATES_PER_BRANCH,
            "rrf_k": RRF_K,
            "top_n": top_n,
        },
    ).fetchall()

    return [
        Passage(
            chunk_id=str(r["chunk_id"]),
            document_id=str(r["document_id"]),
            version_id=str(r["version_id"]),
            title=r["title"],
            page=r["page"],
            heading=r["heading"],
            text=r["text"] or "",
            score_dense=float(r["score_dense"]),
            score_fts=float(r["score_fts"]),
            rrf=float(r["rrf"]),
        )
        for r in rows
    ]
