"""analytics_events, idempotency_keys, crawl_jobs, preview conversations

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-24

Closes the remaining schema gaps from docs/16-API-ROUTES.md and
docs/19-BACKEND-SPRINT-PLAN-V2.md:

- analytics_events: Phase 6 ("write analytics_events rows for
  message-sent / feedback-given / conversation-started").
- idempotency_keys: replay-safe storage for bot/publish and other owner
  mutations that require an Idempotency-Key header.
- crawl_jobs: async crawl discovery (POST /sources/crawl/discover,
  GET /crawl-jobs/{id}, POST /crawl-jobs/{id}/import).
- conversations: owner draft preview conversations have no visitor
  session and may have no publication, so those columns become nullable
  and an is_preview flag is added.
- messages.client_key: per-conversation Idempotency-Key for chat sends.
- leads: consent timestamp + one lead per conversation.
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE analytics_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            bot_id uuid REFERENCES bots(id) ON DELETE CASCADE,
            conversation_id uuid REFERENCES conversations(id) ON DELETE SET NULL,
            message_id uuid REFERENCES messages(id) ON DELETE SET NULL,
            event_type text NOT NULL
                CHECK (event_type IN ('conversation_started','message_sent','feedback_given','lead_submitted','answer_no_evidence','quota_blocked')),
            properties jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX analytics_events_company_idx ON analytics_events(company_id, created_at)")
    op.execute("CREATE INDEX analytics_events_type_idx ON analytics_events(company_id, event_type)")

    op.execute(
        """
        CREATE TABLE idempotency_keys (
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            scope text NOT NULL,
            key text NOT NULL,
            request_fingerprint text NOT NULL,
            status_code integer NOT NULL,
            response jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (company_id, scope, key)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE crawl_jobs (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            root_url text NOT NULL,
            max_pages integer NOT NULL,
            status text NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','running','completed','failed')),
            discovered_pages jsonb NOT NULL DEFAULT '[]'::jsonb,
            error_code text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX crawl_jobs_company_idx ON crawl_jobs(company_id, created_at)")

    op.execute("ALTER TABLE conversations ALTER COLUMN visitor_session_id DROP NOT NULL")
    op.execute("ALTER TABLE conversations ALTER COLUMN publication_id DROP NOT NULL")
    op.execute("ALTER TABLE conversations ADD COLUMN is_preview boolean NOT NULL DEFAULT false")
    op.execute(
        """
        ALTER TABLE conversations ADD CONSTRAINT conversations_actor_check
        CHECK (is_preview OR (visitor_session_id IS NOT NULL AND publication_id IS NOT NULL))
        """
    )

    op.execute("ALTER TABLE messages ADD COLUMN client_key text")
    op.execute(
        "CREATE UNIQUE INDEX messages_conversation_client_key_idx ON messages(conversation_id, client_key) WHERE client_key IS NOT NULL"
    )

    op.execute("ALTER TABLE leads ADD COLUMN consent_at timestamptz")
    op.execute("CREATE UNIQUE INDEX leads_one_per_conversation_idx ON leads(conversation_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS leads_one_per_conversation_idx")
    op.execute("ALTER TABLE leads DROP COLUMN IF EXISTS consent_at")
    op.execute("DROP INDEX IF EXISTS messages_conversation_client_key_idx")
    op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS client_key")
    op.execute("ALTER TABLE conversations DROP CONSTRAINT IF EXISTS conversations_actor_check")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS is_preview")
    op.execute("DROP TABLE IF EXISTS crawl_jobs")
    op.execute("DROP TABLE IF EXISTS idempotency_keys")
    op.execute("DROP TABLE IF EXISTS analytics_events")
