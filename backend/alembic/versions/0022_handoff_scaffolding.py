"""Handoff scaffolding (D5.5): add status/assigned_to columns to conversations,
and a canned_replies table for quick human responses.

Revision ID: 0022
Revises: 0021
Create Date: 2026-11-27
"""
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'bot'")
    op.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS assigned_to uuid REFERENCES users(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS handed_off_at timestamptz")
    op.execute("CREATE INDEX IF NOT EXISTS idx_conversations_status ON conversations (status) WHERE status != 'bot'")

    op.execute(
        """
        CREATE TABLE canned_replies (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            title text NOT NULL,
            body text NOT NULL,
            shortcut text,
            sort_order int NOT NULL DEFAULT 0,
            active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("ALTER TABLE canned_replies ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY canned_replies_tenant_isolation ON canned_replies
        FOR ALL
        USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
        WITH CHECK (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON canned_replies TO app_user")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS canned_replies")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS handed_off_at")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS assigned_to")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS status")
