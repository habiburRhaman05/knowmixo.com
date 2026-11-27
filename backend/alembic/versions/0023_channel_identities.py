"""Channel scaffolding (D6.1/D6.4): bot_channel_bindings maps an external
Meta account (WhatsApp phone_number_id, Messenger Page id, Instagram
account id) to a bot; channel_identities maps an external sender to the
synthetic visitor_session + conversation that carries their turns through
the existing chat pipeline unchanged.

Revision ID: 0023
Revises: 0022
Create Date: 2026-11-27
"""
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None

_TENANT_TABLES = ["bot_channel_bindings", "channel_identities"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE bot_channel_bindings (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            bot_id uuid NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            channel text NOT NULL CHECK (channel IN ('whatsapp','messenger','instagram')),
            external_account_id text NOT NULL,
            active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (channel, external_account_id)
        )
        """
    )
    op.execute("CREATE INDEX idx_bot_channel_bindings_company ON bot_channel_bindings (company_id)")

    op.execute(
        """
        CREATE TABLE channel_identities (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            bot_id uuid NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            channel text NOT NULL CHECK (channel IN ('whatsapp','messenger','instagram')),
            external_id text NOT NULL,
            visitor_session_id uuid NOT NULL REFERENCES visitor_sessions(id) ON DELETE CASCADE,
            conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (bot_id, channel, external_id)
        )
        """
    )
    op.execute("CREATE INDEX idx_channel_identities_company ON channel_identities (company_id)")

    for table in _TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table}_tenant_isolation ON {table}
            FOR ALL
            USING (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
            WITH CHECK (company_id = NULLIF(current_setting('app.company_id', true), '')::uuid)
            """
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO app_user")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS channel_identities")
    op.execute("DROP TABLE IF EXISTS bot_channel_bindings")
