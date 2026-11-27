"""Billing scaffolding (ADR 008, launch/09-BILLING-PAYMENTS.md §3): plans,
subscriptions, usage_events, invoices, stripe_events. Seeds the plan
matrix from §1/§2. No Checkout/Portal/entitlements yet (Day 4, D4.3) and
no UI -- this is schema + the Stripe webhook ingestion endpoint only.

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-26
"""
import json

from alembic import op
from sqlalchemy import text

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

# (id, name, interval, stripe_lookup_key, limits, features, sort_order)
# limits: null means "unlimited". analytics_retention_days / sla_hours:
# null means no SLA / no retention guarantee beyond the default.
_PLANS = [
    (
        "free", "Free", "month", "free",
        {"ai_replies_per_month": 100, "sources": 3, "storage_mb": 20, "bots": 1, "members": 1, "analytics_retention_days": 7},
        {"channels": ["widget"], "sla_hours": None, "whatsapp": False, "sms": False, "shopify": False, "hubspot": False, "api": False, "multi_workspace": False},
        0,
    ),
    (
        "starter_monthly", "Starter · Monthly", "month", "starter_monthly",
        {"ai_replies_per_month": 2000, "sources": 20, "storage_mb": 200, "bots": 1, "members": 2, "analytics_retention_days": 30},
        {"channels": ["widget", "slack"], "sla_hours": None, "whatsapp": False, "sms": False, "shopify": False, "hubspot": False, "api": False, "multi_workspace": False},
        10,
    ),
    (
        "starter_yearly", "Starter · Yearly", "year", "starter_yearly",
        {"ai_replies_per_month": 2000, "sources": 20, "storage_mb": 200, "bots": 1, "members": 2, "analytics_retention_days": 30},
        {"channels": ["widget", "slack"], "sla_hours": None, "whatsapp": False, "sms": False, "shopify": False, "hubspot": False, "api": False, "multi_workspace": False},
        11,
    ),
    (
        "growth_monthly", "Growth · Monthly", "month", "growth_monthly",
        {"ai_replies_per_month": 10000, "sources": 100, "storage_mb": 2000, "bots": 3, "members": 5, "analytics_retention_days": 90},
        {"channels": ["widget", "slack", "whatsapp", "sms"], "sla_hours": 48, "whatsapp": True, "sms": True, "shopify": False, "hubspot": False, "api": False, "multi_workspace": False},
        20,
    ),
    (
        "growth_yearly", "Growth · Yearly", "year", "growth_yearly",
        {"ai_replies_per_month": 10000, "sources": 100, "storage_mb": 2000, "bots": 3, "members": 5, "analytics_retention_days": 90},
        {"channels": ["widget", "slack", "whatsapp", "sms"], "sla_hours": 48, "whatsapp": True, "sms": True, "shopify": False, "hubspot": False, "api": False, "multi_workspace": False},
        21,
    ),
    (
        "scale_monthly", "Scale · Monthly", "month", "scale_monthly",
        {"ai_replies_per_month": 40000, "sources": None, "storage_mb": 20000, "bots": 10, "members": 15, "analytics_retention_days": 365},
        {"channels": ["widget", "slack", "whatsapp", "sms", "shopify", "hubspot"], "sla_hours": 24, "whatsapp": True, "sms": True, "shopify": True, "hubspot": True, "api": True, "multi_workspace": False},
        30,
    ),
    (
        "scale_yearly", "Scale · Yearly", "year", "scale_yearly",
        {"ai_replies_per_month": 40000, "sources": None, "storage_mb": 20000, "bots": 10, "members": 15, "analytics_retention_days": 365},
        {"channels": ["widget", "slack", "whatsapp", "sms", "shopify", "hubspot"], "sla_hours": 24, "whatsapp": True, "sms": True, "shopify": True, "hubspot": True, "api": True, "multi_workspace": False},
        31,
    ),
    (
        "agency_monthly", "Agency · Monthly", "month", "agency_monthly",
        {"ai_replies_per_month": 120000, "sources": None, "storage_mb": 100000, "bots": 50, "members": 50, "analytics_retention_days": 730},
        {"channels": ["widget", "slack", "whatsapp", "sms", "shopify", "hubspot"], "sla_hours": 8, "whatsapp": True, "sms": True, "shopify": True, "hubspot": True, "api": True, "multi_workspace": True},
        40,
    ),
    (
        "agency_yearly", "Agency · Yearly", "year", "agency_yearly",
        {"ai_replies_per_month": 120000, "sources": None, "storage_mb": 100000, "bots": 50, "members": 50, "analytics_retention_days": 730},
        {"channels": ["widget", "slack", "whatsapp", "sms", "shopify", "hubspot"], "sla_hours": 8, "whatsapp": True, "sms": True, "shopify": True, "hubspot": True, "api": True, "multi_workspace": True},
        41,
    ),
    (
        "overage_reply", "Overage · 1,000 AI replies", "metered", "overage_reply",
        {"ai_replies_per_unit": 1000},
        {"metered": True},
        100,
    ),
]

_TENANT_TABLES = ["subscriptions", "usage_events", "invoices"]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE plans (
            id text PRIMARY KEY,
            name text NOT NULL,
            interval text NOT NULL,
            stripe_lookup_key text UNIQUE,
            limits jsonb NOT NULL,
            features jsonb NOT NULL,
            sort_order int NOT NULL,
            active boolean NOT NULL DEFAULT true
        )
        """
    )
    bind = op.get_bind()
    for plan_id, name, interval, lookup_key, limits, features, sort_order in _PLANS:
        bind.execute(
            text(
                """
                INSERT INTO plans (id, name, interval, stripe_lookup_key, limits, features, sort_order)
                VALUES (:id, :name, :interval, :lookup_key, CAST(:limits AS jsonb), CAST(:features AS jsonb), :sort_order)
                """
            ),
            {
                "id": plan_id,
                "name": name,
                "interval": interval,
                "lookup_key": lookup_key,
                "limits": json.dumps(limits),
                "features": json.dumps(features),
                "sort_order": sort_order,
            },
        )

    op.execute(
        """
        CREATE TABLE subscriptions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            stripe_customer_id text UNIQUE,
            stripe_subscription_id text UNIQUE,
            plan_id text NOT NULL REFERENCES plans(id),
            status text NOT NULL,
            current_period_start timestamptz,
            current_period_end timestamptz,
            cancel_at_period_end boolean NOT NULL DEFAULT false,
            paused_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX idx_subscriptions_company_id ON subscriptions (company_id)")

    op.execute(
        """
        CREATE TABLE usage_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            conversation_id uuid REFERENCES conversations(id) ON DELETE SET NULL,
            kind text NOT NULL,
            quantity numeric(12,4) NOT NULL,
            period_start timestamptz,
            period_end timestamptz,
            reported_to_stripe_at timestamptz,
            stripe_meter_event_id text,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX usage_events_company_period ON usage_events (company_id, period_start)")

    op.execute(
        """
        CREATE TABLE invoices (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            stripe_invoice_id text UNIQUE,
            amount_cents int NOT NULL,
            currency text NOT NULL DEFAULT 'usd',
            status text NOT NULL,
            hosted_url text,
            pdf_url text,
            period_start timestamptz,
            period_end timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX idx_invoices_company_id ON invoices (company_id)")

    # Global Stripe event ingestion log -- NOT tenant-scoped (a raw webhook
    # delivery isn't yet correlated to a company until processed; the
    # stripe_customer_id -> company_id lookup happens in the processor,
    # same as 09-BILLING-PAYMENTS.md §4 describes). Only the bypass-role
    # webhook endpoint and its background processor ever touch this table,
    # so it is deliberately NOT granted to app_user and has no RLS policy.
    op.execute(
        """
        CREATE TABLE stripe_events (
            event_id text PRIMARY KEY,
            type text NOT NULL,
            created_at timestamptz NOT NULL,
            received_at timestamptz NOT NULL DEFAULT now(),
            payload jsonb NOT NULL,
            processed_at timestamptz
        )
        """
    )
    op.execute("CREATE INDEX idx_stripe_events_unprocessed ON stripe_events (received_at) WHERE processed_at IS NULL")

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

    # plans is a shared read-only catalog, not a tenant table -- every
    # company can read it, none can write it through the app role.
    op.execute("GRANT SELECT ON plans TO app_user")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS stripe_events")
    op.execute("DROP TABLE IF EXISTS invoices")
    op.execute("DROP TABLE IF EXISTS usage_events")
    op.execute("DROP TABLE IF EXISTS subscriptions")
    op.execute("DROP TABLE IF EXISTS plans")
