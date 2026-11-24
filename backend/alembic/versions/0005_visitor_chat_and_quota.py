"""visitor_sessions, conversations, messages, leads, feedback, usage

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-23

Phase 4 + 5 scope per docs/19-BACKEND-SPRINT-PLAN-V2.md:
- Sprint 4: visitor_sessions, conversations, messages (with status, generation_id,
  citations JSONB, usage JSONB), leads, feedback
- Sprint 5: usage_reservations, usage_daily (quota budget enforcement before chat goes live)
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Visitor sessions: short-lived bot-scoped tokens for public chat
    op.execute(
        """
        CREATE TABLE visitor_sessions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            bot_id uuid NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            session_token_hash text NOT NULL,
            expires_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT visitor_sessions_token_hash_unique UNIQUE (session_token_hash)
        )
        """
    )
    op.execute("CREATE INDEX visitor_sessions_bot_idx ON visitor_sessions(bot_id)")
    op.execute("CREATE INDEX visitor_sessions_expires_idx ON visitor_sessions(expires_at)")

    # Conversations: link visitor session to a bot/publication
    op.execute(
        """
        CREATE TABLE conversations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            bot_id uuid NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
            publication_id uuid NOT NULL REFERENCES publications(id) ON DELETE RESTRICT,
            visitor_session_id uuid NOT NULL REFERENCES visitor_sessions(id) ON DELETE CASCADE,
            status text NOT NULL DEFAULT 'active' CHECK (status IN ('active','closed')),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX conversations_bot_idx ON conversations(bot_id)")
    op.execute("CREATE INDEX conversations_visitor_session_idx ON conversations(visitor_session_id)")

    # Messages: the core chat turn with citations, usage, status
    op.execute(
        """
        CREATE TABLE messages (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role text NOT NULL CHECK (role IN ('user','assistant')),
            content text NOT NULL,
            status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','streaming','completed','interrupted','failed')),
            generation_id uuid,
            citations jsonb,
            usage jsonb,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX messages_conversation_idx ON messages(conversation_id, created_at)")

    # Leads: captured via lead form trigger (post_hoc initially)
    op.execute(
        """
        CREATE TABLE leads (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            message_id uuid REFERENCES messages(id) ON DELETE SET NULL,
            lead_form_id uuid NOT NULL REFERENCES lead_forms(id) ON DELETE RESTRICT,
            values jsonb NOT NULL,
            submitted_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX leads_conversation_idx ON leads(conversation_id)")

    # Feedback: per-message, actor can be visitor or owner, unique per message+actor
    op.execute(
        """
        CREATE TABLE feedback (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            message_id uuid NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
            actor text NOT NULL CHECK (actor IN ('visitor','owner')),
            actor_id uuid,
            rating integer NOT NULL CHECK (rating IN (-1, 1)),
            comment text,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT feedback_message_actor_unique UNIQUE (message_id, actor, actor_id)
        )
        """
    )
    op.execute("CREATE INDEX feedback_message_idx ON feedback(message_id)")

    # Quota: daily budget tracking
    op.execute(
        """
        CREATE TABLE usage_daily (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            date date NOT NULL,
            embeddings_count integer NOT NULL DEFAULT 0,
            chat_tokens_count integer NOT NULL DEFAULT 0,
            chat_requests_count integer NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT usage_daily_company_date_unique UNIQUE (company_id, date)
        )
        """
    )

    # Quota reservations: prevents oversubscription race on concurrent requests
    op.execute(
        """
        CREATE TABLE usage_reservations (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            conversation_id uuid REFERENCES conversations(id) ON DELETE CASCADE,
            estimated_tokens integer NOT NULL,
            status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','committed','released')),
            expires_at timestamptz NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX usage_reservations_company_idx ON usage_reservations(company_id, status)")
    op.execute("CREATE INDEX usage_reservations_conversation_idx ON usage_reservations(conversation_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS usage_reservations")
    op.execute("DROP TABLE IF EXISTS usage_daily")
    op.execute("DROP TABLE IF EXISTS feedback")
    op.execute("DROP TABLE IF EXISTS leads")
    op.execute("DROP TABLE IF EXISTS messages")
    op.execute("DROP TABLE IF EXISTS conversations")
    op.execute("DROP TABLE IF EXISTS visitor_sessions")