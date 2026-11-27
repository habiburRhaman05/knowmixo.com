"""Roles + team invites (D8.6, launch/01-FEATURE-INVENTORY.md K.5/K.6,
launch/02-GAP-ANALYSIS.md). Relaxes memberships.role from owner-only to
owner/admin/agent/viewer, and adds an invites table for email-based
team invites with a role pre-selected by the inviter.

Every existing user already has exactly one 'owner' membership row
(both signup paths insert one in the same transaction as the company),
so relaxing the CHECK constraint is purely additive -- no backfill needed.

Revision ID: 0026
Revises: 0025
Create Date: 2026-11-27
"""
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE memberships DROP CONSTRAINT IF EXISTS memberships_role_check")
    op.execute(
        "ALTER TABLE memberships ADD CONSTRAINT memberships_role_check CHECK (role IN ('owner','admin','agent','viewer'))"
    )

    op.execute(
        """
        CREATE TABLE invites (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            email text NOT NULL,
            role text NOT NULL CHECK (role IN ('admin','agent','viewer')),
            token_hash text NOT NULL,
            invited_by uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at timestamptz NOT NULL,
            accepted_at timestamptz,
            revoked_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT invites_token_hash_unique UNIQUE (token_hash)
        )
        """
    )
    op.execute("CREATE INDEX idx_invites_company ON invites (company_id)")
    op.execute(
        "CREATE UNIQUE INDEX idx_invites_pending_email ON invites (company_id, email) WHERE accepted_at IS NULL AND revoked_at IS NULL"
    )

    op.execute("ALTER TABLE invites ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY invites_tenant_isolation ON invites
        FOR ALL
        USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
        WITH CHECK (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON invites TO app_user")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS invites")
    op.execute("ALTER TABLE memberships DROP CONSTRAINT IF EXISTS memberships_role_check")
    op.execute("UPDATE memberships SET role = 'owner' WHERE role != 'owner'")
    op.execute("ALTER TABLE memberships ADD CONSTRAINT memberships_role_check CHECK (role IN ('owner'))")
