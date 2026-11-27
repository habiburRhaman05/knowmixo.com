"""Allow escalations.conversation_id to be NULL for test alerts
(launch/06-ESCALATION-DESIGN.md §10: POST /escalations/test runs the
real delivery path with no real conversation behind it). Mirrors the
conversations table's own is_preview/nullable-FK pattern from migration
0008. NULL is never equal to NULL in a unique index, so test rows never
collide with each other or with real escalations in escalations_dedupe.

Revision ID: 0024
Revises: 0023
Create Date: 2026-11-27
"""
from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE escalations ALTER COLUMN conversation_id DROP NOT NULL")
    op.execute(
        """
        ALTER TABLE escalations ADD CONSTRAINT escalations_test_or_conversation_check
        CHECK (test OR conversation_id IS NOT NULL)
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM escalations WHERE conversation_id IS NULL")
    op.execute("ALTER TABLE escalations DROP CONSTRAINT IF EXISTS escalations_test_or_conversation_check")
    op.execute("ALTER TABLE escalations ALTER COLUMN conversation_id SET NOT NULL")
