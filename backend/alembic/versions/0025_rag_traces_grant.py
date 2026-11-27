"""Fix: migration 0019 enabled RLS on rag_traces but never granted
app_user table privileges, unlike every other tenant table's migration
(0011, 0014, 0020, 0021, 0022, 0023 all GRANT the owning role). Without
this, app_user can see zero rows regardless of its RLS policy once the
app's pool switches off the current RLS-bypass role.

Revision ID: 0025
Revises: 0024
Create Date: 2026-11-27
"""
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON rag_traces TO app_user")


def downgrade() -> None:
    op.execute("REVOKE SELECT, INSERT, UPDATE, DELETE ON rag_traces FROM app_user")
