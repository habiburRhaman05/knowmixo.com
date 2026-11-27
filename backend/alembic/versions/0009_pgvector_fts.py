"""pgvector + FTS columns on chunks (ADR 001 / launch/05-RAG-V2-SPEC.md §6)

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-25

Adds hybrid-retrieval infrastructure for RAG v2:

- `vector` extension so we can store dense embeddings in Postgres.
- `chunks.embedding vector(1024)` — matches EMBEDDING_DIM.
- `chunks.tsvector tsvector` — populated by a trigger that concatenates
  the heading + text columns. Keeps retrieval symmetric with the dense
  path because both read from the same row.
- `chunks.language text` — ISO 639-1; populated from the document version
  at ingest time (Day 3 pipeline). Nullable for backward compatibility.
- HNSW index on the embedding (fast similarity search with recall/latency
  tuning via (m, ef_construction)).
- GIN index on the tsvector (fast FTS).
- Composite index on (company_id, version_id) used by the hybrid query's
  metadata filter.

The 72-h dual-write window described in ADR 001 is implemented in
`app/ingestion/pipeline.py` on Day 3. During the window, reads still go to
Pinecone until the flag `settings.vector_store == 'pgvector'` flips.

Rollback: dropping the HNSW/GIN indexes and the columns is safe (no data
is lost — Pinecone still has the primary copy).
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pgvector is maintained by Neon; `CREATE EXTENSION IF NOT EXISTS` is
    # idempotent and only requires the owner role once.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Add columns to chunks. chunks already has: id, version_id, ordinal,
    # page, heading, text, vector_id, checksum, created_at.
    # New columns are nullable so the migration is non-blocking.
    op.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS embedding vector(1024)")
    op.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS tsvector tsvector")
    op.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS language text")

    # A trigger keeps tsvector in sync with heading + text. We use the
    # `english` dictionary for now; language-aware config comes on Day 3
    # when ingestion populates chunks.language. Falling back to 'simple'
    # for non-English chunks avoids the Postgres FTS dictionary gap.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION chunks_tsvector_update() RETURNS trigger AS $$
        BEGIN
          NEW.tsvector :=
            setweight(to_tsvector(COALESCE(NEW.language, 'simple')::regconfig,
                                  COALESCE(NEW.heading, '')), 'A')
            || setweight(to_tsvector(COALESCE(NEW.language, 'simple')::regconfig,
                                     COALESCE(NEW.text, '')), 'B');
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute("DROP TRIGGER IF EXISTS chunks_tsvector_trg ON chunks")
    op.execute(
        """
        CREATE TRIGGER chunks_tsvector_trg
        BEFORE INSERT OR UPDATE OF heading, text, language ON chunks
        FOR EACH ROW EXECUTE FUNCTION chunks_tsvector_update()
        """
    )

    # HNSW index parameters: m=16, ef_construction=64 — pgvector defaults
    # that work well for 1024-d cosine similarity at launch scale. We can
    # tune later per the benchmarking plan in launch/05 §9.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS chunks_embedding_hnsw
        ON chunks USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS chunks_tsvector_gin ON chunks USING gin (tsvector)")

    # We need `company_id` on chunks for the RLS policy in migration 0010
    # and for the hybrid query's primary filter. chunks today reaches
    # company_id by join through document_versions -> documents. Adding a
    # denormalised column saves one join and makes the RLS policy trivial.
    op.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS company_id uuid")
    op.execute(
        """
        UPDATE chunks c SET company_id = d.company_id
        FROM document_versions dv
        JOIN documents d ON d.id = dv.document_id
        WHERE c.version_id = dv.id AND c.company_id IS NULL
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS chunks_company_version_idx
        ON chunks (company_id, version_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS chunks_company_version_idx")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS company_id")
    op.execute("DROP INDEX IF EXISTS chunks_tsvector_gin")
    op.execute("DROP INDEX IF EXISTS chunks_embedding_hnsw")
    op.execute("DROP TRIGGER IF EXISTS chunks_tsvector_trg ON chunks")
    op.execute("DROP FUNCTION IF EXISTS chunks_tsvector_update()")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS language")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS tsvector")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS embedding")
    # Leaving the `vector` extension in place: it's shared and dropping it
    # would break anything else in the DB that uses it.
