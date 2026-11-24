"""lead_forms, lead_form_fields

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-23

Phase 5 scope, per docs/19-BACKEND-SPRINT-PLAN-V2.md Phase 5: brought
forward from the original single "migration 0004" in
docs/18-DATABASE-V2-V3-SCALABLE-SCHEMA.md because lead_forms/
lead_form_fields depend only on bots, which already exists.

lead_submissions is deliberately NOT created here, unlike doc 18's
original grouping -- it has a real FK dependency on conversations(id),
which does not exist until Phase 6. Creating it now would mean either a
dangling/unenforced FK or a fake placeholder table, neither of which is
better than creating it correctly alongside conversations in Phase 6's
migration. This is a sequencing correction discovered while implementing
Phase 5, not a silently dropped requirement.
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE lead_forms (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            bot_id uuid NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            name text NOT NULL,
            trigger text NOT NULL DEFAULT 'post_hoc'
                CHECK (trigger IN ('post_hoc','before_chat_start','after_n_messages','exit_intent')),
            trigger_config jsonb NOT NULL DEFAULT '{}'::jsonb,
            is_required boolean NOT NULL DEFAULT false,
            is_active boolean NOT NULL DEFAULT true,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX lead_forms_bot_idx ON lead_forms(bot_id)")

    op.execute(
        """
        CREATE TABLE lead_form_fields (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            lead_form_id uuid NOT NULL REFERENCES lead_forms(id) ON DELETE CASCADE,
            field_key text NOT NULL,
            label text NOT NULL,
            field_type text NOT NULL CHECK (field_type IN ('text','email','phone','select','checkbox','textarea')),
            is_required boolean NOT NULL DEFAULT false,
            options jsonb,
            sort_order integer NOT NULL DEFAULT 0,
            CONSTRAINT lead_form_fields_form_key_unique UNIQUE (lead_form_id, field_key)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lead_form_fields")
    op.execute("DROP TABLE IF EXISTS lead_forms")
