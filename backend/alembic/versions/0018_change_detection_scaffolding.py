"""Change-detection scaffolding (D3.5): lets a URL/crawl-page document be
periodically re-checked for upstream changes without re-embedding content
that hasn't moved. Scaffolding only -- the owner-facing schedule UI for
setting check_interval_hours per source is Day 7 (D7.x); nothing here is
reachable from an API endpoint yet.

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-27
"""
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents ADD COLUMN check_interval_hours integer")
    op.execute("ALTER TABLE documents ADD COLUMN last_checked_at timestamptz")
    op.execute("ALTER TABLE documents ADD COLUMN source_checksum text")
    op.execute(
        "CREATE INDEX idx_documents_change_detection_due ON documents (last_checked_at) "
        "WHERE check_interval_hours IS NOT NULL AND deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_documents_change_detection_due")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS source_checksum")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS last_checked_at")
    op.execute("ALTER TABLE documents DROP COLUMN IF EXISTS check_interval_hours")
