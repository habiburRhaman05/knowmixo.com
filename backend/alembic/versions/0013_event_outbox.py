"""Event outbox (ADR 003): event_outbox table feeding a dispatch_event job
executor, fanning out to webhook_deliveries.

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-26

Per ADR 003, producers insert into `event_outbox` in the SAME transaction
as the domain change they're reporting (e.g. a conversation starting), so
the event can never be silently dropped by a crash between the domain
write and the event write. A `dispatch_event` executor on the existing
jobs runner (app/jobs/executors.py) reads the referenced row and fans out
to `webhook_deliveries` for every active endpoint subscribed to that
topic. Idempotent on `(company_id, topic, payload_hash)` -- re-emitting
the same logical event (e.g. a retried request) is a no-op, not a
duplicate webhook delivery.

launch/01-FEATURE-INVENTORY.md H.5: "webhook_endpoints + webhook_deliveries
tables + delivery worker exist; no application code emits events today."
This migration is the missing piece -- it does not touch the existing
delivery worker (app/webhooks/worker.py), which already claims and POSTs
whatever rows land in webhook_deliveries.
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE event_outbox (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            bot_id uuid REFERENCES bots(id) ON DELETE CASCADE,
            topic text NOT NULL,
            payload jsonb NOT NULL,
            payload_hash text NOT NULL,
            dispatched_at timestamptz,
            attempts int NOT NULL DEFAULT 0,
            next_try_at timestamptz NOT NULL DEFAULT now(),
            dead_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (company_id, topic, payload_hash)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_event_outbox_pending
        ON event_outbox (next_try_at)
        WHERE dispatched_at IS NULL AND dead_at IS NULL
        """
    )
    op.execute("CREATE INDEX idx_event_outbox_company_id ON event_outbox (company_id)")

    op.execute("ALTER TABLE event_outbox ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY event_outbox_tenant_isolation ON event_outbox
        FOR ALL
        USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
        WITH CHECK (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON event_outbox TO app_user")

    # Links a delivery back to the outbox event that produced it, so the
    # dispatch_event executor can fan out idempotently: if it's retried
    # after a crash partway through notifying N endpoints, re-running it
    # must not double-insert deliveries for endpoints it already reached.
    op.execute("ALTER TABLE webhook_deliveries ADD COLUMN event_outbox_id uuid REFERENCES event_outbox(id) ON DELETE CASCADE")
    op.execute(
        """
        CREATE UNIQUE INDEX idx_webhook_deliveries_event_endpoint
        ON webhook_deliveries (event_outbox_id, endpoint_id)
        WHERE event_outbox_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_webhook_deliveries_event_endpoint")
    op.execute("ALTER TABLE webhook_deliveries DROP COLUMN IF EXISTS event_outbox_id")
    op.execute("DROP TABLE IF EXISTS event_outbox")
