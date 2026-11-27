"""rag_traces (D4.2, launch/05-RAG-V2-SPEC.md section 6): one row per
assistant turn run through the v2 pipeline, read by Day 7's Playground
retrieval inspector. RLS follows the same tenant-isolation pattern as
every table migration 0011 enabled -- this table postdates that
migration, so it needs its own policy rather than inheriting one.

Revision ID: 0019
Revises: 0018
Create Date: 2026-11-27
"""
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

_POLICY_EXPR = "company_id = NULLIF(current_setting('app.company_id', true), '')::uuid"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE rag_traces (
          id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
          conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
          message_id uuid NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
          intent text, severity text, language text,
          rewritten_queries jsonb NOT NULL DEFAULT '[]',
          retrieved jsonb NOT NULL DEFAULT '[]',
          reranked jsonb NOT NULL DEFAULT '[]',
          grade_iterations int NOT NULL DEFAULT 0,
          tools_used jsonb NOT NULL DEFAULT '[]',
          verifier_result jsonb,
          tokens_in int, tokens_out int,
          latency_ms_total int NOT NULL DEFAULT 0,
          latency_ms_per_stage jsonb NOT NULL DEFAULT '{}',
          provider text, model text,
          cost_est_cents numeric(10,4),
          abstained boolean NOT NULL DEFAULT false,
          escalated boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX rag_traces_company_message ON rag_traces(company_id, message_id)")
    op.execute("CREATE INDEX rag_traces_conversation ON rag_traces(conversation_id)")

    op.execute("ALTER TABLE rag_traces ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY rag_traces_tenant_isolation ON rag_traces
        FOR ALL
        USING ({_POLICY_EXPR})
        WITH CHECK ({_POLICY_EXPR})
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS rag_traces")
