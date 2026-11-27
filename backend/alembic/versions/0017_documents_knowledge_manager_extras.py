"""Knowledge manager backend extras (D3.6): size_bytes, disabled_at, tags
on documents. Schema only -- no endpoint/UI yet (Day 7's Knowledge UI
finish, D7.4, ships the disabled toggle + size + last-synced display;
bulk actions + tags UI are flagged NEEDS_MORE_TIME per
launch/12-FEASIBILITY-MATRIX.md and are out of scope there too).

Revision ID: 0017
Revises: 0016
Create Date: 2026-11-26
"""
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents ADD COLUMN size_bytes bigint")
    op.execute("ALTER TABLE documents ADD COLUMN disabled_at timestamptz")
    op.execute("ALTER TABLE documents ADD COLUMN tags text[] NOT NULL DEFAULT '{}'")
    op.execute("CREATE INDEX idx_documents_disabled_at ON documents (disabled_at) WHERE disabled_at IS NOT NULL")
    op.execute("CREATE INDEX idx_documents_tags ON documents USING gin (tags)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_documents_tags")
    op.execute("DROP INDEX IF EXISTS idx_documents_disabled_at")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS tags")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS disabled_at")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS size_bytes")
