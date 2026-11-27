"""Auto-populate company_id on INSERT for the 14 fanned-out tables (fixes a
regression migration 0010 would otherwise have introduced)

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-26

Migration 0010 added `company_id NOT NULL` to 14 tables and backfilled
EXISTING rows. It did not -- and could not, being a one-time data
migration -- teach the application's existing INSERT statements (scattered
across `app/bots/service.py`, `app/sources/service.py`,
`app/public/router.py`, etc.) to populate that column for NEW rows. Left
as-is, the very next `INSERT INTO publications`, `INSERT INTO
conversations`, `INSERT INTO messages`, etc. from the live app -- which
predates these columns existing at all -- would fail with a NOT NULL
violation. Caught by `test/api/test_rls_fail_closed.py`'s
`test_deep_table_feedback_three_hops_is_isolated` test before this ever
reached the live app.

Rather than hunting down and patching every INSERT call site (error-prone
-- a missed site fails the same way, and future code can reintroduce the
same gap), each of the 14 tables gets a `BEFORE INSERT` trigger that
resolves `company_id` from its immediate parent row when the caller
didn't supply it. This closes the gap for every current AND future
insert path uniformly, at the one place that actually enforces the
constraint. Mirrors the `chunks.tsvector` trigger pattern from migration
0009, which is already proven in production use.

If a caller DOES supply company_id explicitly (e.g. a future, properly
updated service-layer call, or the RLS-bound app_user role where the
value naturally flows from the request's tenant context), the trigger
trusts it as-is and does not override it.
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

# (table, source_table, fk_column_on_child) -- the direct parent to read
# company_id from. Order doesn't matter here (unlike 0010's one-time
# backfill): each trigger fires at insert-time, and the parent row must
# already exist by then (FK constraint), so its own company_id -- set
# either by a prior migration's backfill or by its own trigger -- is
# already correct.
_TRIGGERED_TABLES = [
    ("bot_domains", "bots", "bot_id"),
    ("bot_links", "bots", "bot_id"),
    ("document_versions", "documents", "document_id"),
    ("job_attempts", "jobs", "job_id"),
    ("lead_forms", "bots", "bot_id"),
    ("publications", "bots", "bot_id"),
    ("visitor_sessions", "bots", "bot_id"),
    ("webhook_deliveries", "webhook_endpoints", "endpoint_id"),
    ("conversations", "bots", "bot_id"),
    ("lead_form_fields", "lead_forms", "lead_form_id"),
    ("messages", "conversations", "conversation_id"),
    ("publication_sources", "publications", "publication_id"),
    ("leads", "conversations", "conversation_id"),
    ("feedback", "messages", "message_id"),
]


def _function_name(table: str) -> str:
    return f"{table}_autopopulate_company_id"


def _trigger_name(table: str) -> str:
    return f"{table}_company_id_trg"


def upgrade() -> None:
    for table, source_table, fk_column in _TRIGGERED_TABLES:
        fn = _function_name(table)
        trg = _trigger_name(table)
        op.execute(
            f"""
            CREATE OR REPLACE FUNCTION {fn}() RETURNS trigger AS $$
            BEGIN
              IF NEW.company_id IS NULL THEN
                SELECT company_id INTO NEW.company_id
                FROM {source_table} WHERE id = NEW.{fk_column};
                IF NEW.company_id IS NULL THEN
                  RAISE EXCEPTION
                    'cannot resolve company_id for {table}: {source_table}.id = % not found',
                    NEW.{fk_column};
                END IF;
              END IF;
              RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(f"DROP TRIGGER IF EXISTS {trg} ON {table}")
        op.execute(
            f"""
            CREATE TRIGGER {trg}
            BEFORE INSERT ON {table}
            FOR EACH ROW EXECUTE FUNCTION {fn}()
            """
        )


def downgrade() -> None:
    for table, _source_table, _fk_column in reversed(_TRIGGERED_TABLES):
        op.execute(f"DROP TRIGGER IF EXISTS {_trigger_name(table)} ON {table}")
        op.execute(f"DROP FUNCTION IF EXISTS {_function_name(table)}()")
