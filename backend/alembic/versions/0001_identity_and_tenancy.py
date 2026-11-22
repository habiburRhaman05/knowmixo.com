"""identity and tenancy: users, oauth_accounts, sessions, auth_tokens, companies, memberships

Revision ID: 0001
Revises:
Create Date: 2026-11-22

Phase 1 target schema per docs/13-DB-ENGINEERING-GAP-ANALYSIS.md and
docs/05-DATABASE.md. Additive only -- does not touch the legacy demo tables
in backend/infra/schema.sql (documents, feedback, audit_events, approvals,
chat_messages), which are superseded table-by-table in later migrations.
"""
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute(
        """
        CREATE TABLE users (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            normalized_email text NOT NULL,
            email text NOT NULL,
            password_hash text,
            name text,
            avatar_key text,
            email_verified_at timestamptz,
            disabled_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT users_normalized_email_unique UNIQUE (normalized_email)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE oauth_accounts (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            provider text NOT NULL,
            provider_subject text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT oauth_accounts_provider_subject_unique UNIQUE (provider, provider_subject)
        )
        """
    )
    op.execute("CREATE INDEX oauth_accounts_user_idx ON oauth_accounts(user_id)")

    op.execute(
        """
        CREATE TABLE sessions (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash text NOT NULL,
            expires_at timestamptz NOT NULL,
            revoked_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT sessions_token_hash_unique UNIQUE (token_hash)
        )
        """
    )
    op.execute("CREATE INDEX sessions_user_idx ON sessions(user_id, expires_at)")

    op.execute(
        """
        CREATE TABLE auth_tokens (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            purpose text NOT NULL CHECK (purpose IN ('verify_email','reset_password','change_email')),
            token_hash text NOT NULL,
            pending_email text,
            expires_at timestamptz NOT NULL,
            consumed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT auth_tokens_token_hash_unique UNIQUE (token_hash)
        )
        """
    )
    op.execute("CREATE INDEX auth_tokens_user_purpose_idx ON auth_tokens(user_id, purpose)")

    op.execute(
        """
        CREATE TABLE companies (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            owner_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name text NOT NULL,
            website text,
            industry text,
            contact text,
            logo_key text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz,
            CONSTRAINT companies_owner_user_id_unique UNIQUE (owner_user_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE memberships (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id uuid NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            role text NOT NULL DEFAULT 'owner' CHECK (role IN ('owner')),
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT memberships_company_user_unique UNIQUE (company_id, user_id)
        )
        """
    )
    op.execute("CREATE INDEX memberships_user_idx ON memberships(user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memberships")
    op.execute("DROP TABLE IF EXISTS companies")
    op.execute("DROP TABLE IF EXISTS auth_tokens")
    op.execute("DROP TABLE IF EXISTS sessions")
    op.execute("DROP TABLE IF EXISTS oauth_accounts")
    op.execute("DROP TABLE IF EXISTS users")
