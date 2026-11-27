# ADR 001 — Vector store and hybrid retrieval

**Status**: Decided 2026-11-25. Implementation Day 3.

## Context

Section 2B of the master prompt mandates hybrid retrieval (dense + BM25/FTS) with metadata filters and RRF fusion, plus a reranker. Current code (`backend/app/providers/vector_store.py`, `app/chat/pipeline.py:retrieve`) uses only Pinecone with a hard-coded 0.25 similarity threshold.

We must decide: keep Pinecone (plus a separate FTS somewhere), or consolidate on Postgres with `pgvector`.

## Options

### A — Keep Pinecone + add Postgres FTS alongside

- Pros: no data migration; Pinecone starter is free.
- Cons: hybrid retrieval becomes two round-trips with app-side RRF; tenant isolation lives in Pinecone namespaces (correct today) **and** also in Postgres RLS — two surfaces to keep aligned; delete-on-cleanup already ships (`providers/vector_store.py:95`) but ingestion + query latency doubles.
- Cost: Pinecone starter free tier caps at 2 GB storage, 5 M vectors, 1 index. 100 chars × average 50 chunks × avg 1000 docs ≈ 50 M vectors — we'd blow this inside the first 200 free-beta users.

### B — pgvector + Postgres FTS (chosen)

- Pros: single SQL query gets dense + FTS + metadata filters + RLS + joins in one call. One store means one ACID boundary. Neon supports pgvector 0.7+ with HNSW index.
- Cons: migration effort; Neon storage cost scales with data (still cheap: 1 GB ≈ $0.35 at retail).
- Known constraint: Neon free tier has 0.5 GB storage. Before Day 3 the storage estimate for 150-user beta: 150 companies × 10 MB vectors avg = 1.5 GB — fits the first paid Neon tier ($19/mo).

### C — Qdrant Cloud free tier

- Pros: fast, modern.
- Cons: another vendor, still separate from Postgres, hybrid is only native in paid tier.

## Decision

**Option B: consolidate on `pgvector` + Postgres full-text search, with RRF performed in a single SQL CTE.**

Rationale: single data boundary matches our tenant-isolation goal (ADR 002), single query reduces chat-latency variance, and the data volume for the next 12 months fits the first paid Neon tier comfortably.

## Trade-offs

- **Risk**: Neon storage growth. Mitigation: `retention_days` worker + source size caps + Day 10 cost review.
- **Risk**: HNSW rebuilds under concurrent writes can spike latency. Mitigation: build index concurrently; write to a shadow index + swap for large data loads.
- **Lock-in**: pgvector is open source; switching to Qdrant later is a well-worn migration.

## Implementation plan

1. Alembic 0009 — add `embedding vector(1024)` and `tsvector` columns to `chunks`; HNSW index `(embedding vector_cosine_ops)`; GIN index on `tsvector`.
2. Dual-write: new ingestion writes to both Pinecone and pgvector for the first 72 hours as a safety net.
3. Switch `retrieve()` to a single hybrid SQL query:
   ```sql
   WITH dense AS (SELECT id, 1 - (embedding <=> $1) AS score FROM chunks
                  WHERE company_id = current_setting('app.company_id')::uuid
                  AND version_id = ANY($2) ORDER BY embedding <=> $1 LIMIT 30),
        fts   AS (SELECT id, ts_rank_cd(tsvector, plainto_tsquery($3)) AS score FROM chunks
                  WHERE company_id = current_setting('app.company_id')::uuid
                  AND version_id = ANY($2) AND tsvector @@ plainto_tsquery($3) LIMIT 30),
        rrf   AS (SELECT id, 1.0/(60 + rank) AS rrf_score FROM (
                     SELECT id, row_number() OVER (ORDER BY score DESC) AS rank FROM dense
                     UNION ALL
                     SELECT id, row_number() OVER (ORDER BY score DESC) AS rank FROM fts
                  ) s)
   SELECT id, SUM(rrf_score) FROM rrf GROUP BY id ORDER BY 2 DESC LIMIT 30;
   ```
4. After the dual-write window, archive and disable Pinecone writes; leave the adapter in the code for rollback.
5. Backfill: migrate existing `chunks` rows from Pinecone with a one-off worker job.

## Rollback

Flip `settings.vector_store = 'pinecone'`; the adapter module stays. All new chunks go back to Pinecone; the pgvector columns remain but are read-only.
