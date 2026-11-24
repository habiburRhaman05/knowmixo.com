"""audit_events, domain allowlist, embed config

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-23

Sprint 5 scope per docs/19-BACKEND-SPRINT-PLAN-V2.md:
- audit_events rebuilt with company_id, actor_id FK, target_id, request_id, safe_metadata
- drop legacy approvals table (explicit sign-off per agent rule 3)
- domain allowlist (bot_domains table)
- embed script/config endpoints data
- conversation export/retention scaffolding
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # audit_events: every mutation tracked with company_id, actor FK, request_id
    op.execute(
        """
        CREATE TABLE audit_events (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            actor text NOT NULL CHECK (actor IN ('visitor','owner')),
            actor_id uuid NOT NULL,
            target_id uuid,
            target_type text NOT NULL CHECK (target_type IN ('bot','conversation','message','source','document','publication','lead_form','job')),
            action text NOT NULL,
            request_id text NOT NULL,
            safe_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX audit_events_company_idx ON audit_events(company_id, created_at)")
    op.execute("CREATE INDEX audit_events_actor_idx ON audit_events(actor, actor_id)")
    op.execute("CREATE INDEX audit_events_request_idx ON audit_events(request_id)")

    # domain allowlist: vetted domains per bot
    op.execute(
        """
        CREATE TABLE bot_domains (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            bot_id uuid NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            domain text NOT NULL,
            is_verified boolean NOT NULL DEFAULT false,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (bot_id, domain)
        )
        """
    )
    op.execute("CREATE INDEX bot_domains_bot_idx ON bot_domains(bot_id)")

    # Drop legacy approvals table if it exists (agent rule 3: explicit sign-off)
    op.execute("DROP TABLE IF EXISTS approvals")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bot_domains")
    op.execute("DROP TABLE IF EXISTS audit_events")