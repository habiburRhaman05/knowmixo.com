"""Public API keys (D9.4, launch/adr/007-api-conventions.md): exact
schema from the ADR -- api_keys(id, company_id, prefix, hashed, scopes
jsonb, last_used_at, created_by, revoked_at). Secret shown once at
creation; hashed with Argon2id (same primitive as passwords).

Revision ID: 0031
Revises: 0030
Create Date: 2026-11-27
"""
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE api_keys (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name text NOT NULL DEFAULT 'API key',
            prefix text NOT NULL,
            hashed text NOT NULL,
            scopes jsonb NOT NULL DEFAULT '[]',
            last_used_at timestamptz,
            created_by uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            revoked_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT api_keys_prefix_unique UNIQUE (prefix)
        )
        """
    )
    op.execute("CREATE INDEX idx_api_keys_company ON api_keys (company_id)")

    op.execute("ALTER TABLE api_keys ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY api_keys_tenant_isolation ON api_keys
        FOR ALL
        USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
        WITH CHECK (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON api_keys TO app_user")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS api_keys")
