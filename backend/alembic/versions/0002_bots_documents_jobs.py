"""bots, documents, document_versions, chunks, jobs, job_attempts

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-23

Phase 2 target schema per docs/13-DB-ENGINEERING-GAP-ANALYSIS.md and
docs/18-DATABASE-V2-V3-SCALABLE-SCHEMA.md migration sequencing. Does not
create publications/publication_sources/bot_links yet -- those are
Migration 0003 (Phase 4), which also adds the deferred FK from
bots.active_publication_id once the publications table exists.
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The legacy demo schema (backend/infra/schema.sql) defines its own
    # `documents` table (tenant_id as free text, s3_key, no company/bot/
    # version model) which collides by name with the real `documents`
    # table created below. docs/13-DB-ENGINEERING-GAP-ANALYSIS.md already
    # concluded this legacy table only ever held demo placeholder rows
    # (owner_sub/actor were literal "demo-operator" values, not real
    # users) and recommended dropping rather than migrating it -- there is
    # no real customer data behind it to preserve. feedback/approvals/
    # chat_messages are dropped for the same reason; audit_events is left
    # alone here and rebuilt in a later migration instead.
    op.execute("DROP TABLE IF EXISTS documents CASCADE")
    op.execute("DROP TABLE IF EXISTS feedback CASCADE")
    op.execute("DROP TABLE IF EXISTS approvals CASCADE")
    op.execute("DROP TABLE IF EXISTS chat_messages CASCADE")

    op.execute(
        """
        CREATE TABLE bots (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            public_id text NOT NULL,
            draft_config jsonb NOT NULL DEFAULT '{}'::jsonb,
            draft_revision integer NOT NULL DEFAULT 1,
            active_publication_id uuid,
            disabled_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT bots_public_id_unique UNIQUE (public_id)
        )
        """
    )
    op.execute("CREATE INDEX bots_company_idx ON bots(company_id)")

    op.execute(
        """
        CREATE TABLE documents (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            bot_id uuid NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            kind text NOT NULL CHECK (kind IN ('file','text','faq','url','crawl_page')),
            title text NOT NULL,
            source_url text,
            storage_key text,
            active_version_id uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz
        )
        """
    )
    op.execute("CREATE INDEX documents_company_bot_idx ON documents(company_id, bot_id, deleted_at)")

    op.execute(
        """
        CREATE TABLE document_versions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            version integer NOT NULL,
            checksum text,
            status text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','processing','retrying','quota_wait','ready','failed','retired')),
            stage text CHECK (stage IN ('validate','extract','chunk','embed','upsert','finalize')),
            chunk_count integer NOT NULL DEFAULT 0,
            embedding_model text,
            dimensions integer,
            error_code text,
            ready_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT document_versions_document_version_unique UNIQUE (document_id, version)
        )
        """
    )
    op.execute("CREATE INDEX document_versions_status_idx ON document_versions(document_id, status)")

    # Deferred FK now that document_versions exists.
    op.execute(
        """
        ALTER TABLE documents
        ADD CONSTRAINT documents_active_version_fk
        FOREIGN KEY (active_version_id) REFERENCES document_versions(id) ON DELETE SET NULL
        """
    )

    op.execute(
        """
        CREATE TABLE chunks (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            version_id uuid NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
            ordinal integer NOT NULL,
            page integer,
            heading text,
            text text,
            vector_id text NOT NULL,
            checksum text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT chunks_version_ordinal_unique UNIQUE (version_id, ordinal),
            CONSTRAINT chunks_vector_id_unique UNIQUE (vector_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE jobs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            document_version_id uuid REFERENCES document_versions(id) ON DELETE CASCADE,
            kind text NOT NULL,
            queue_kind text NOT NULL DEFAULT 'main' CHECK (queue_kind IN ('main','retry','dead')),
            state text NOT NULL DEFAULT 'queued'
                CHECK (state IN ('queued','processing','quota_wait','succeeded','dead')),
            stage text,
            attempts integer NOT NULL DEFAULT 0,
            max_attempts integer NOT NULL DEFAULT 4,
            available_at timestamptz NOT NULL DEFAULT now(),
            lease_token uuid,
            lease_expires_at timestamptz,
            checkpoint_ref jsonb,
            error_code text,
            idempotency_key text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT jobs_idempotency_key_unique UNIQUE (idempotency_key)
        )
        """
    )
    op.execute("CREATE INDEX jobs_claim_idx ON jobs(queue_kind, state, available_at)")
    op.execute("CREATE INDEX jobs_lease_idx ON jobs(lease_expires_at)")
    op.execute("CREATE INDEX jobs_company_idx ON jobs(company_id)")

    op.execute(
        """
        CREATE TABLE job_attempts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            job_id uuid NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            attempt integer NOT NULL,
            lease_token uuid NOT NULL,
            started_at timestamptz NOT NULL DEFAULT now(),
            ended_at timestamptz,
            stage text,
            safe_error text,
            CONSTRAINT job_attempts_job_attempt_unique UNIQUE (job_id, attempt)
        )
        """
    )


def downgrade() -> None:
    # Does not recreate the dropped legacy demo tables (documents,
    # feedback, approvals, chat_messages) -- they are permanently retired
    # per the architecture decision in this migration's upgrade(), not
    # paused. A downgrade only removes what Phase 2 added.
    op.execute("DROP TABLE IF EXISTS job_attempts")
    op.execute("DROP TABLE IF EXISTS jobs")
    op.execute("DROP TABLE IF EXISTS chunks")
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_active_version_fk")
    op.execute("DROP TABLE IF EXISTS document_versions")
    op.execute("DROP TABLE IF EXISTS documents")
    op.execute("DROP TABLE IF EXISTS bots")
