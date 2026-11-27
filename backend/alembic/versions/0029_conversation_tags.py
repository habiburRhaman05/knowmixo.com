"""Conversation tags (D8.1, launch/13-SPRINT-10-DAYS.md: "schema only;
UI label Day 11"). A plain text[] column is sufficient for owner-defined
free-form tags -- no separate tags table/vocabulary is specified, and
filtering by overlap (&&) with a GIN index is enough for the filter use
case this sprint needs.

Revision ID: 0029
Revises: 0028
Create Date: 2026-11-27
"""
from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE conversations ADD COLUMN tags text[] NOT NULL DEFAULT '{}'")
    op.execute("CREATE INDEX idx_conversations_tags ON conversations USING gin (tags)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_conversations_tags")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS tags")
