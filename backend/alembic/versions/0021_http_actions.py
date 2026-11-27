"""HTTP actions table for owner-defined webhook actions
(launch/13-SPRINT-10-DAYS.md D5.2).

Revision ID: 0021
Revises: 0020
Create Date: 2026-11-27
"""
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE http_actions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            bot_id uuid NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            name text NOT NULL,
            description text,
            method text NOT NULL DEFAULT 'POST' CHECK (method IN ('GET','POST','PUT','PATCH','DELETE')),
            url text NOT NULL,
            headers jsonb NOT NULL DEFAULT '{}',
            body_template jsonb,
            timeout_ms int NOT NULL DEFAULT 5000,
            active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX idx_http_actions_company ON http_actions (company_id)")
    op.execute("CREATE INDEX idx_http_actions_bot ON http_actions (bot_id)")

    op.execute("ALTER TABLE http_actions ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY http_actions_tenant_isolation ON http_actions
        FOR ALL
        USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
        WITH CHECK (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON http_actions TO app_user")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS http_actions")
