"""MFA: TOTP + recovery codes (D8.5, launch/01-FEATURE-INVENTORY.md K.4).
No spec exists beyond the one-line backlog item + library hint (pyotp) --
data model and endpoints are this session's from-scratch design.

mfa_secret is set on setup, confirmed (mfa_enabled_at set) only after the
owner proves possession with a real TOTP code -- a secret with no
mfa_enabled_at is "pending setup", not active, and resolve_session must
never trust an unconfirmed secret as a factor. Recovery codes are stored
hashed (one-way, single-use) in their own table so each is independently
revocable/consumable, same shape as auth_tokens.

Revision ID: 0028
Revises: 0027
Create Date: 2026-11-27
"""
from alembic import op

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN mfa_secret text")
    op.execute("ALTER TABLE users ADD COLUMN mfa_enabled_at timestamptz")

    op.execute(
        """
        CREATE TABLE mfa_recovery_codes (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            code_hash text NOT NULL,
            used_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute("CREATE INDEX idx_mfa_recovery_codes_user ON mfa_recovery_codes (user_id)")

    # Step-up tokens prove MFA was verified recently enough to authorize a
    # destructive action. Short-lived and single-use, same shape as
    # auth_tokens; not tenant-scoped since it hangs off a user, not a company.
    op.execute(
        """
        CREATE TABLE mfa_step_up_tokens (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash text NOT NULL,
            expires_at timestamptz NOT NULL,
            consumed_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT mfa_step_up_tokens_token_hash_unique UNIQUE (token_hash)
        )
        """
    )
    op.execute("CREATE INDEX idx_mfa_step_up_tokens_user ON mfa_step_up_tokens (user_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mfa_step_up_tokens")
    op.execute("DROP TABLE IF EXISTS mfa_recovery_codes")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS mfa_enabled_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS mfa_secret")
