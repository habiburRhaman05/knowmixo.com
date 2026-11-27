"""Slack app installations (D9.5): OAuth install flow result per
company, used for alerts channel delivery.

Revision ID: 0032
Revises: 0031
Create Date: 2026-11-27
"""
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE slack_installations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            team_id text NOT NULL,
            team_name text,
            access_token text NOT NULL,
            bot_user_id text,
            incoming_webhook_url text,
            incoming_webhook_channel text,
            installed_by uuid REFERENCES users(id) ON DELETE SET NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT slack_installations_company_unique UNIQUE (company_id)
        )
        """
    )
    op.execute("ALTER TABLE slack_installations ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY slack_installations_tenant_isolation ON slack_installations
        FOR ALL
        USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
        WITH CHECK (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON slack_installations TO app_user")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS slack_installations")
