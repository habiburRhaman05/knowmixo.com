"""publications, publication_sources, bot_links

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-23

Phase 4 target schema per docs/13-DB-ENGINEERING-GAP-ANALYSIS.md and
docs/18-DATABASE-V2-V3-SCALABLE-SCHEMA.md migration sequencing. Adds the
deferred FK from bots.active_publication_id now that publications exists
(mirrors the documents.active_version_id pattern in migration 0002).
bot_links is modeled now but not wired into the chat pipeline until V2
(docs/18).
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE publications (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            bot_id uuid NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            version integer NOT NULL,
            config_snapshot jsonb NOT NULL,
            prompt_version text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT publications_bot_version_unique UNIQUE (bot_id, version)
        )
        """
    )
    op.execute("CREATE INDEX publications_bot_idx ON publications(bot_id)")

    op.execute(
        """
        CREATE TABLE publication_sources (
            publication_id uuid NOT NULL REFERENCES publications(id) ON DELETE CASCADE,
            document_version_id uuid NOT NULL REFERENCES document_versions(id) ON DELETE RESTRICT,
            PRIMARY KEY (publication_id, document_version_id)
        )
        """
    )

    # Deferred FK now that publications exists (bots was created first in
    # migration 0002 since a bot can exist in draft with no publication yet).
    op.execute(
        """
        ALTER TABLE bots
        ADD CONSTRAINT bots_active_publication_fk
        FOREIGN KEY (active_publication_id) REFERENCES publications(id) ON DELETE SET NULL
        """
    )

    op.execute(
        """
        CREATE TABLE bot_links (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            bot_id uuid NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            document_id uuid REFERENCES documents(id) ON DELETE SET NULL,
            label text NOT NULL,
            url text NOT NULL,
            keywords text[] NOT NULL DEFAULT '{}',
            is_active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX bot_links_bot_idx ON bot_links(bot_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bot_links")
    op.execute("ALTER TABLE bots DROP CONSTRAINT IF EXISTS bots_active_publication_fk")
    op.execute("DROP TABLE IF EXISTS publication_sources")
    op.execute("DROP TABLE IF EXISTS publications")
