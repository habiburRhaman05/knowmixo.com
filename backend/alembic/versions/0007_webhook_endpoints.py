"""webhook_endpoints, webhook_deliveries for Phase 7 webhook scaffolding

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-23

Phase 7 scope per docs/19-BACKEND-SPRINT-PLAN-V2.md:
- webhook_endpoints: configurable HTTP endpoints per company/bot
- webhook_deliveries: delivery attempts with retry logic, using Phase 2 job runner pattern
- Tables built now, reusing job-runner pattern for delivery retries - dormant until V2 turns it on
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # webhook_endpoints: configurable HTTP endpoints per company/bot
    op.execute(
        """
        CREATE TABLE webhook_endpoints (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            bot_id uuid REFERENCES bots(id) ON DELETE SET NULL,
            url text NOT NULL,
            secret text NOT NULL,
            events text[] NOT NULL DEFAULT '{}',
            is_active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX webhook_endpoints_company_idx ON webhook_endpoints(company_id)")
    op.execute("CREATE INDEX webhook_endpoints_bot_idx ON webhook_endpoints(bot_id)")

    # webhook_deliveries: delivery attempts with retry logic
    # Uses Phase 2 job runner pattern: status, attempts, next_retry_at, last_error
    op.execute(
        """
        CREATE TABLE webhook_deliveries (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            endpoint_id uuid NOT NULL REFERENCES webhook_endpoints(id) ON DELETE CASCADE,
            event_type text NOT NULL,
            payload jsonb NOT NULL,
            status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','delivered','failed','dead')),
            attempt integer NOT NULL DEFAULT 0,
            max_attempts integer NOT NULL DEFAULT 5,
            next_retry_at timestamptz,
            last_error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            delivered_at timestamptz
        )
        """
    )
    op.execute("CREATE INDEX webhook_deliveries_endpoint_idx ON webhook_deliveries(endpoint_id, status)")
    op.execute("CREATE INDEX webhook_deliveries_retry_idx ON webhook_deliveries(next_retry_at) WHERE status = 'pending'")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS webhook_deliveries")
    op.execute("DROP TABLE IF EXISTS webhook_endpoints")