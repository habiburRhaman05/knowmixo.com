"""Escalation engine tables (launch/06-ESCALATION-DESIGN.md §1):
escalation_rules, escalation_contacts, escalations, escalation_attempts.

Revision ID: 0020
Revises: 0019
Create Date: 2026-11-27
"""
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

_TENANT_TABLES = ["escalation_rules", "escalation_contacts", "escalations", "escalation_attempts"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE escalation_rules (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            name text NOT NULL,
            match jsonb NOT NULL,
            severity text NOT NULL CHECK (severity IN ('critical','high','medium','low')),
            active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE escalation_contacts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            channel text NOT NULL CHECK (channel IN ('whatsapp','sms','email','slack','telegram','push')),
            address text NOT NULL,
            verified_at timestamptz,
            priority int NOT NULL,
            quiet_hours_tz text,
            quiet_hours_start time,
            quiet_hours_end time,
            active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE escalations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            rule_id uuid REFERENCES escalation_rules(id) ON DELETE SET NULL,
            severity text NOT NULL,
            reason_summary text NOT NULL,
            ai_summary text NOT NULL,
            key_details jsonb NOT NULL DEFAULT '{}',
            state text NOT NULL CHECK (state IN ('created','queued','sent','delivered','acknowledged','failed','dead')),
            acknowledged_at timestamptz,
            acknowledged_by uuid REFERENCES users(id),
            acknowledged_channel text,
            deep_link_jti uuid NOT NULL,
            test boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    # date_trunc on timestamptz is not IMMUTABLE (depends on session TZ).
    # Use an expression that truncates to the minute in UTC explicitly.
    op.execute(
        """
        CREATE UNIQUE INDEX escalations_dedupe
        ON escalations (conversation_id, severity, date_trunc('minute', created_at AT TIME ZONE 'UTC'))
        """
    )

    op.execute(
        """
        CREATE TABLE escalation_attempts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            escalation_id uuid NOT NULL REFERENCES escalations(id) ON DELETE CASCADE,
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            attempt int NOT NULL,
            channel text NOT NULL,
            address text NOT NULL,
            provider_message_id text,
            state text NOT NULL,
            error_code text,
            started_at timestamptz NOT NULL DEFAULT now(),
            ended_at timestamptz
        )
        """
    )

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
    op.execute("DROP TABLE IF EXISTS escalation_attempts")
    op.execute("DROP TABLE IF EXISTS escalations")
    op.execute("DROP TABLE IF EXISTS escalation_contacts")
    op.execute("DROP TABLE IF EXISTS escalation_rules")
