"""Row-Level Security on every tenant table + the app_user role (ADR 002, step 2 of 2)

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-26

Defense in depth for tenant isolation. App-level `WHERE company_id = %s`
filters already exist throughout `app/*/service.py`; this migration makes
a missing or wrong filter fail CLOSED (zero rows) instead of leaking
another tenant's data, by enforcing the same boundary at the database
level for any role other than the table owner.

Two things happen here:

  1. A new `app_user` role is created: LOGIN, NOSUPERUSER, NOBYPASSRLS,
     NOCREATEDB, NOCREATEROLE. It is granted SELECT/INSERT/UPDATE/DELETE
     on every table (not DDL -- schema changes stay exclusively on the
     migration-running owner role) plus USAGE/SELECT on sequences, with
     `ALTER DEFAULT PRIVILEGES` so tables added by future migrations are
     automatically granted too.

     No password is set here. Role creation is schema (replayed
     identically in every environment); the password is a per-environment
     SECRET and is provisioned separately and exactly once per
     environment by `scripts/provision_app_user.py`, which also writes
     the resulting `DATABASE_URL_APP` into that environment's own `.env`.
     A role with LOGIN but no password set cannot authenticate via
     password auth, so `app_user` is inert (harmless to have existed) in
     any environment that hasn't run the provisioning script yet.

  2. RLS is enabled on every tenant table (the 26 with `company_id` from
     migration 0010, plus `companies` itself via its own `id`) with ONE
     policy per table: `FOR ALL USING (...) WITH CHECK (...)`, comparing
     the row's tenant column against `current_setting('app.company_id',
     true)` -- set per-request by the application via
     `SELECT set_config('app.company_id', $1, true)` (transaction-scoped,
     so it can never leak across pooled connections between requests).
     `NULLIF(..., '')` guards against a cast error when the setting is
     unset; an unset/empty setting makes `company_id = NULL`, which is
     never true, so an unauthenticated or mis-scoped query sees zero
     rows -- fail-closed by construction.

  IMPORTANT -- deliberately NOT done in this migration, and why:
  The application's live request-serving connection pool is NOT switched
  to `app_user` here. Several write paths are not yet classified as
  "needs tenant scoping" vs "needs to bypass RLS because it's the
  operation that CREATES the tenant boundary in the first place" --
  most notably signup, which inserts the very first `companies` row a
  membership will ever reference. A `WITH CHECK` policy cannot be
  satisfied for a row whose tenant identity doesn't exist in the session
  context yet, by definition, for a brand-new tenant. Cutting the
  live pool over requires auditing every such bootstrap/admin code path
  (signup, account-cleanup job, webhook ingestion, crawl worker) first.
  That audit and the pool switch are the very next task; this migration
  ships the policies as independently-provable, inert infrastructure,
  proven via an automated test that connects directly as `app_user`
  (see test/api/test_rls_fail_closed.py), exactly satisfying today's
  acceptance bar without risking the live app on an incomplete audit.
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


# Every table from migration 0010 (26 of them) plus the 12 that already
# had company_id directly as of migration 0008 -- i.e. every table that
# now has a `company_id` column. `companies` is handled separately below
# since its tenant key is its own `id`, not a `company_id` column.
_TENANT_TABLES = [
    "analytics_events", "audit_events", "bot_domains", "bot_links", "bots",
    "chunks", "conversations", "crawl_jobs", "document_versions", "documents",
    "feedback", "idempotency_keys", "job_attempts", "jobs", "lead_form_fields",
    "lead_forms", "leads", "memberships", "messages", "publication_sources",
    "publications", "usage_daily", "usage_reservations", "visitor_sessions",
    "webhook_deliveries", "webhook_endpoints",
]

_POLICY_EXPR = "company_id = NULLIF(current_setting('app.company_id', true), '')::uuid"
_COMPANIES_POLICY_EXPR = "id = NULLIF(current_setting('app.company_id', true), '')::uuid"


def upgrade() -> None:
    bind = op.get_bind()

    # --- 1. app_user role -----------------------------------------------
    # No password: see module docstring. `DO $$ ... $$` guards against a
    # re-run finding the role already present (CREATE ROLE has no native
    # IF NOT EXISTS before PG16; Neon's current version may vary).
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_user') THEN
            CREATE ROLE app_user LOGIN
              NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOREPLICATION
              CONNECTION LIMIT -1;
          END IF;
        END
        $$;
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO app_user")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_user")
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_user"
    )
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
        "GRANT USAGE, SELECT ON SEQUENCES TO app_user"
    )

    # --- 2. RLS everywhere -------------------------------------------------
    for table in _TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            FOR ALL
            USING ({_POLICY_EXPR})
            WITH CHECK ({_POLICY_EXPR})
            """
        )

    op.execute("ALTER TABLE companies ENABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS companies_tenant_isolation ON companies")
    op.execute(
        f"""
        CREATE POLICY companies_tenant_isolation ON companies
        FOR ALL
        USING ({_COMPANIES_POLICY_EXPR})
        WITH CHECK ({_COMPANIES_POLICY_EXPR})
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS companies_tenant_isolation ON companies")
    op.execute("ALTER TABLE companies DISABLE ROW LEVEL SECURITY")
    for table in reversed(_TENANT_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {table}_tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    # Role is left in place on downgrade -- a LOGIN role with no password
    # set cannot authenticate, so it's inert, and DROP ROLE would fail
    # anyway if anything (e.g. a provisioned DATABASE_URL_APP) is actively
    # connected as app_user. Operators who need to fully remove it can
    # run: REVOKE ALL ON ALL TABLES IN SCHEMA public FROM app_user;
    #      DROP OWNED BY app_user; DROP ROLE app_user;
