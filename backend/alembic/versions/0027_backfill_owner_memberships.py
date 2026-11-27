"""Data-hygiene backfill: some existing companies have an owner_user_id
with no corresponding 'owner' membership row (likely created before
memberships existed, or by a path that predates _create_user_with_company
always inserting one). Confirmed against the real DB: 7 of 29 users hit
this. app.auth.service.resolve_session now resolves company_id primarily
via memberships, so this gap would silently log those owners out of
their own company without this backfill.

Revision ID: 0027
Revises: 0026
Create Date: 2026-11-27
"""
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO memberships (company_id, user_id, role)
        SELECT c.id, c.owner_user_id, 'owner'
        FROM companies c
        WHERE c.deleted_at IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM memberships m
              WHERE m.company_id = c.id AND m.user_id = c.owner_user_id
          )
        """
    )


def downgrade() -> None:
    pass  # backfill is a one-way data fix, not reversible (and not destructive to leave in place)
