"""Denormalize company_id onto every tenant-owned table (ADR 002, step 1 of 2)

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-26

RLS policies (migration 0011) need a `company_id` column to filter on
every tenant table. Today only 12 tables have it directly; the rest reach
it only via a join chain (e.g. `messages -> conversations -> bots ->
companies`). Per ADR 002, we denormalize `company_id` onto every such
table rather than writing RLS policies with subqueries, because:

  1. A subquery-based policy re-runs the join on every row check, which
     is both slower and harder to index correctly.
  2. A flat `company_id = current_setting(...)` policy is trivial to
     reason about and trivial to test for fail-closed behaviour.
  3. We already did exactly this for `chunks` in migration 0009.

Tables deliberately EXCLUDED from this migration (and from RLS in 0011):
`users`, `sessions`, `auth_tokens`, `oauth_accounts` -- these are scoped
by `user_id`, not `company_id`. A user is not a tenant; the company they
own is. Isolation for these tables is the existing `resolve_session`
lookup-by-token mechanism, which is a different (and already tested)
boundary than cross-tenant leakage.

`companies` itself is also excluded from this migration (it doesn't need
a `company_id` column -- its own `id` IS the tenant identifier; its RLS
policy in 0011 compares `id` directly).

Backfill is layered in dependency order so each table can copy
`company_id` from a table that already has it by the time we reach it:

  Layer 1 (from bots/documents/jobs/webhook_endpoints, which already have
  company_id as of 0001-0008):
    bot_domains, bot_links, document_versions, job_attempts, lead_forms,
    publications, visitor_sessions, webhook_deliveries, conversations

  Layer 2 (from Layer 1 tables):
    lead_form_fields (<- lead_forms), messages (<- conversations),
    publication_sources (<- publications), leads (<- conversations)

  Layer 3 (from Layer 2 tables):
    feedback (<- messages)

Every new column is added nullable, backfilled, indexed, then made
NOT NULL -- never blocking reads mid-migration, and the final NOT NULL
constraint is the proof the backfill covered every row.
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


# (table, source_table, source_fk_column) -- source_table already has
# company_id populated by the time this table's backfill runs, given the
# layering above.
_LAYER_1 = [
    ("bot_domains", "bots", "bot_id"),
    ("bot_links", "bots", "bot_id"),
    ("document_versions", "documents", "document_id"),
    ("job_attempts", "jobs", "job_id"),
    ("lead_forms", "bots", "bot_id"),
    ("publications", "bots", "bot_id"),
    ("visitor_sessions", "bots", "bot_id"),
    ("webhook_deliveries", "webhook_endpoints", "endpoint_id"),
    ("conversations", "bots", "bot_id"),
]

_LAYER_2 = [
    ("lead_form_fields", "lead_forms", "lead_form_id"),
    ("messages", "conversations", "conversation_id"),
    ("publication_sources", "publications", "publication_id"),
    ("leads", "conversations", "conversation_id"),
]

_LAYER_3 = [
    ("feedback", "messages", "message_id"),
]


def _add_and_backfill(table: str, source_table: str, fk_column: str) -> None:
    op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS company_id uuid")
    op.execute(
        f"""
        UPDATE {table} t SET company_id = s.company_id
        FROM {source_table} s
        WHERE t.{fk_column} = s.id AND t.company_id IS NULL
        """
    )
    op.execute(f"CREATE INDEX IF NOT EXISTS {table}_company_id_idx ON {table} (company_id)")


def upgrade() -> None:
    for table, source_table, fk_column in _LAYER_1:
        _add_and_backfill(table, source_table, fk_column)
    for table, source_table, fk_column in _LAYER_2:
        _add_and_backfill(table, source_table, fk_column)
    for table, source_table, fk_column in _LAYER_3:
        _add_and_backfill(table, source_table, fk_column)

    # Make every newly-added column NOT NULL now that it's backfilled. If
    # any row failed to backfill (orphaned FK, impossible under the
    # existing FK constraints, but we check anyway) this step fails loudly
    # rather than silently shipping a nullable hole in the RLS policy.
    all_tables = [t for t, _, _ in (_LAYER_1 + _LAYER_2 + _LAYER_3)]
    for table in all_tables:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN company_id SET NOT NULL")
        op.execute(
            f"""
            ALTER TABLE {table}
            ADD CONSTRAINT {table}_company_id_fkey
            FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE
            """
        )


def downgrade() -> None:
    all_tables = [t for t, _, _ in (_LAYER_1 + _LAYER_2 + _LAYER_3)]
    for table in reversed(all_tables):
        op.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_company_id_fkey")
        op.execute(f"DROP INDEX IF EXISTS {table}_company_id_idx")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS company_id")
