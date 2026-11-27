"""Gaps + bad-answers queue + alerts (D8.3). Definitions per
launch/MASTER-PROMPT.md §79-82 and launch/12-FEASIBILITY-MATRIX.md:119
(the 3 built-in alert rules are "quota 80/100, unanswered spike,
ingestion failure"); no DB schema or clustering algorithm is specified
anywhere, so the tables and the exact-normalized-text clustering here
are this session's from-scratch design (embedding-based clustering is
the stated future upgrade, same NEEDS_MORE_TIME pattern already used
elsewhere in this project for bulk/tags).

Revision ID: 0030
Revises: 0029
Create Date: 2026-11-27
"""
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None

_TENANT_TABLES = ["gaps", "bad_answer_reviews", "alert_state"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE gaps (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            bot_id uuid NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            normalized_question text NOT NULL,
            sample_question text NOT NULL,
            occurrence_count int NOT NULL DEFAULT 1,
            first_seen_at timestamptz NOT NULL DEFAULT now(),
            last_seen_at timestamptz NOT NULL DEFAULT now(),
            status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved','ignored')),
            resolved_at timestamptz,
            resolved_by uuid REFERENCES users(id),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT gaps_bot_question_unique UNIQUE (bot_id, normalized_question)
        )
        """
    )
    op.execute("CREATE INDEX idx_gaps_company_status ON gaps (company_id, status)")

    op.execute(
        """
        CREATE TABLE bad_answer_reviews (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            message_id uuid NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            reason text NOT NULL,
            status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','corrected','dismissed')),
            correction_text text,
            corrected_by uuid REFERENCES users(id),
            corrected_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT bad_answer_reviews_message_unique UNIQUE (message_id)
        )
        """
    )
    op.execute("CREATE INDEX idx_bad_answer_reviews_company_status ON bad_answer_reviews (company_id, status)")

    # Debounce state for the 3 built-in alert rules -- last time each rule
    # fired per company, so a sustained condition (e.g. quota pinned at
    # 100%) sends one alert, not one per evaluation tick.
    op.execute(
        """
        CREATE TABLE alert_state (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            rule text NOT NULL,
            last_triggered_at timestamptz,
            last_value jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT alert_state_company_rule_unique UNIQUE (company_id, rule)
        )
        """
    )

    for table in _TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            FOR ALL
            USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
            WITH CHECK (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
            """
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO app_user")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS alert_state")
    op.execute("DROP TABLE IF EXISTS bad_answer_reviews")
    op.execute("DROP TABLE IF EXISTS gaps")
