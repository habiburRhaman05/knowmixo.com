"""Auth business logic. No FastAPI imports here -- this module is the
testable core; app/auth/router.py is the thin HTTP adapter.

Security invariants enforced throughout (per docs/02-ACCEPTANCE.md and
docs/11-AGENT-RULES.md):
  - Passwords are Argon2id-hashed, never stored or logged in plaintext.
  - Session/auth tokens are opaque random bearer strings; only their SHA-256
    hash is ever persisted. The raw token is returned to the caller exactly
    once and never recoverable from the database.
  - Signup/forgot-password responses are identical whether or not the
    account exists, to avoid account-enumeration.
  - Password reset revokes all prior sessions for that user.
  - Google sign-in never silently links to an existing email/password
    account -- a collision requires the explicit /me/oauth/google/link flow.
"""
from dataclasses import dataclass

from app.email import (
    send_email_change_confirmation,
    send_password_reset_email,
    send_verification_email,
)
from app.security.passwords import hash_password, verify_password
from app.security.tokens import (
    RESET_PASSWORD_TTL_SECONDS,
    VERIFY_EMAIL_TTL_SECONDS,
    expires_at,
    generate_opaque_token,
    hash_token,
    utcnow,
)

SESSION_TTL_SECONDS_DEFAULT = 60 * 60 * 24 * 7  # 7 days, per 03-TRD.md
RESEND_VERIFICATION_COOLDOWN_SECONDS = 60
FORGOT_PASSWORD_COOLDOWN_SECONDS = 60


def _recent_token_within_cooldown(conn, user_id: str, purpose: str, cooldown_seconds: int) -> bool:
    """DB-based rate-limit shim. Phase 2 introduces Redis for rate limiting
    per docs/03-TRD.md ("Redis accelerates rate limiting") -- this keeps
    the per-purpose cooldown enforced from Phase 1 onward in the meantime,
    rather than leaving forgot-password/resend endpoints fully unbounded."""
    recent = conn.execute(
        """
        SELECT created_at FROM auth_tokens
        WHERE user_id = %s AND purpose = %s
        ORDER BY created_at DESC LIMIT 1
        """,
        (user_id, purpose),
    ).fetchone()
    if not recent:
        return False
    elapsed = (utcnow() - recent["created_at"]).total_seconds()
    return elapsed < cooldown_seconds


class AuthError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def normalize_email(email: str) -> str:
    return email.strip().lower()


@dataclass(frozen=True)
class SessionPrincipal:
    user_id: str
    company_id: str | None
    email: str
    email_verified: bool
    role: str | None = None  # 'owner'|'admin'|'agent'|'viewer', via memberships (D8.6)


# --- Users and companies -----------------------------------------------


def get_user_by_email(conn, email: str):
    return conn.execute(
        "SELECT * FROM users WHERE normalized_email = %s",
        (normalize_email(email),),
    ).fetchone()


def get_user_by_id(conn, user_id: str):
    return conn.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()


def get_company_for_owner(conn, user_id: str):
    return conn.execute(
        "SELECT * FROM companies WHERE owner_user_id = %s AND deleted_at IS NULL",
        (user_id,),
    ).fetchone()


def _create_user_with_company(conn, email: str, name: str, password_hash: str | None):
    """Creates a user, an auto-provisioned company, and the owner membership
    in one transaction. V1 scope: one owner, one company (05-DATABASE.md)."""
    user = conn.execute(
        """
        INSERT INTO users (normalized_email, email, password_hash, name)
        VALUES (%s, %s, %s, %s)
        RETURNING *
        """,
        (normalize_email(email), email, password_hash, name),
    ).fetchone()

    company = conn.execute(
        """
        INSERT INTO companies (owner_user_id, name)
        VALUES (%s, %s)
        RETURNING *
        """,
        (user["id"], f"{name}'s company"),
    ).fetchone()

    conn.execute(
        """
        INSERT INTO memberships (company_id, user_id, role)
        VALUES (%s, %s, 'owner')
        """,
        (company["id"], user["id"]),
    )

    return user, company


# --- Sessions -------------------------------------------------------------


def create_session(conn, user_id: str, ttl_seconds: int = SESSION_TTL_SECONDS_DEFAULT) -> str:
    token = generate_opaque_token()
    conn.execute(
        """
        INSERT INTO sessions (user_id, token_hash, expires_at)
        VALUES (%s, %s, %s)
        """,
        (user_id, hash_token(token), expires_at(ttl_seconds)),
    )
    return token


def revoke_session(conn, token: str) -> None:
    conn.execute(
        "UPDATE sessions SET revoked_at = now() WHERE token_hash = %s AND revoked_at IS NULL",
        (hash_token(token),),
    )


def revoke_all_sessions(conn, user_id: str) -> None:
    conn.execute(
        "UPDATE sessions SET revoked_at = now() WHERE user_id = %s AND revoked_at IS NULL",
        (user_id,),
    )


def resolve_session(conn, token: str) -> SessionPrincipal | None:
    """Fails closed: any missing/expired/revoked session returns None."""
    row = conn.execute(
        """
        SELECT s.user_id, u.email, u.email_verified_at, u.disabled_at
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token_hash = %s
          AND s.revoked_at IS NULL
          AND s.expires_at > now()
        """,
        (hash_token(token),),
    ).fetchone()
    if not row or row["disabled_at"] is not None:
        return None

    # Every signup path inserts an 'owner' membership in the same
    # transaction as the company (_create_user_with_company), so this is
    # purely additive: existing single-company owners resolve exactly as
    # before, and D8.6 invited members (role != 'owner', no owned company
    # of their own) now also resolve a company_id + role here. A user with
    # more than one membership (not a V1-supported shape) gets their owner
    # membership if they have one, else their oldest membership.
    membership = conn.execute(
        """
        SELECT m.company_id, m.role
        FROM memberships m JOIN companies c ON c.id = m.company_id
        WHERE m.user_id = %s AND c.deleted_at IS NULL
        ORDER BY (m.role = 'owner') DESC, m.created_at ASC
        LIMIT 1
        """,
        (row["user_id"],),
    ).fetchone()

    company_id = str(membership["company_id"]) if membership else None
    role = membership["role"] if membership else None

    if company_id is None:
        # Defense in depth: migration 0027 backfilled every pre-existing
        # gap between companies.owner_user_id and memberships (found 7 of
        # 29 real users missing a row), but this direct lookup stays as a
        # permanent safety net so a future insert path that forgets the
        # membership row can never silently log an owner out of their own
        # company.
        owned = conn.execute(
            "SELECT id FROM companies WHERE owner_user_id = %s AND deleted_at IS NULL",
            (row["user_id"],),
        ).fetchone()
        if owned:
            company_id = str(owned["id"])
            role = "owner"

    return SessionPrincipal(
        user_id=str(row["user_id"]),
        company_id=company_id,
        email=row["email"],
        email_verified=row["email_verified_at"] is not None,
        role=role,
    )


# --- Auth tokens (verify email / reset password / change email) -----------


def _create_auth_token(conn, user_id: str, purpose: str, ttl_seconds: int, pending_email: str | None = None) -> str:
    token = generate_opaque_token()
    conn.execute(
        """
        INSERT INTO auth_tokens (user_id, purpose, token_hash, pending_email, expires_at)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (user_id, purpose, hash_token(token), pending_email, expires_at(ttl_seconds)),
    )
    return token


def _consume_auth_token(conn, token: str, purpose: str):
    """Single-use: consumed_at is set atomically in the same statement that
    validates expiry, so a token cannot be replayed even under a race."""
    row = conn.execute(
        """
        UPDATE auth_tokens
        SET consumed_at = now()
        WHERE token_hash = %s
          AND purpose = %s
          AND consumed_at IS NULL
          AND expires_at > now()
        RETURNING user_id, pending_email
        """,
        (hash_token(token), purpose),
    ).fetchone()
    return row


# --- Signup / login --------------------------------------------------------


def signup(conn, email: str, password: str, name: str) -> None:
    """Always succeeds from the caller's perspective (no account-existence
    disclosure) -- if the email is already registered, this is a silent
    no-op that still sends nothing new."""
    existing = get_user_by_email(conn, email)
    if existing:
        return  # Generic accepted response regardless; see router.

    user, _company = _create_user_with_company(conn, email, name, hash_password(password))
    token = _create_auth_token(conn, user["id"], "verify_email", VERIFY_EMAIL_TTL_SECONDS)
    send_verification_email(email, token)


def login_with_password(conn, email: str, password: str) -> dict:
    """Returns {"session_token": ...} as before when MFA is off (the
    unchanged path for every account today), or {"mfa_required": True,
    "mfa_token": ...} when the account has MFA enabled -- the caller
    exchanges mfa_token + a TOTP/recovery code at POST /auth/mfa/login-verify
    for the real session (see app.security.mfa)."""
    user = get_user_by_email(conn, email)
    if not user or not verify_password(password, user["password_hash"]):
        raise AuthError(401, "invalid_credentials", "Email or password is incorrect.")
    if user["disabled_at"] is not None:
        raise AuthError(403, "account_disabled", "This account is disabled.")

    from app.security.mfa import is_mfa_enabled

    if is_mfa_enabled(conn, str(user["id"])):
        from app.security.mfa_login import issue_mfa_login_challenge
        return {"mfa_required": True, "mfa_token": issue_mfa_login_challenge(str(user["id"]))}

    return {"session_token": create_session(conn, user["id"])}


def verify_email(conn, token: str) -> None:
    row = _consume_auth_token(conn, token, "verify_email")
    if not row:
        raise AuthError(410, "token_invalid", "This verification link is invalid or has expired.")
    conn.execute(
        "UPDATE users SET email_verified_at = now() WHERE id = %s AND email_verified_at IS NULL",
        (row["user_id"],),
    )


def resend_verification(conn, email: str) -> None:
    user = get_user_by_email(conn, email)
    if not user or user["email_verified_at"] is not None:
        return  # Generic accepted response regardless of account state.
    if _recent_token_within_cooldown(conn, user["id"], "verify_email", RESEND_VERIFICATION_COOLDOWN_SECONDS):
        return  # Cooldown: silent no-op, still a generic accepted response.
    token = _create_auth_token(conn, user["id"], "verify_email", VERIFY_EMAIL_TTL_SECONDS)
    send_verification_email(email, token)


def forgot_password(conn, email: str) -> None:
    user = get_user_by_email(conn, email)
    if not user:
        return  # Generic accepted response regardless.
    if _recent_token_within_cooldown(conn, user["id"], "reset_password", FORGOT_PASSWORD_COOLDOWN_SECONDS):
        return  # Cooldown: silent no-op, still a generic accepted response.
    token = _create_auth_token(conn, user["id"], "reset_password", RESET_PASSWORD_TTL_SECONDS)
    send_password_reset_email(email, token)


def reset_password(conn, token: str, new_password: str) -> None:
    row = _consume_auth_token(conn, token, "reset_password")
    if not row:
        raise AuthError(410, "token_invalid", "This reset link is invalid or has expired.")
    conn.execute(
        "UPDATE users SET password_hash = %s, updated_at = now() WHERE id = %s",
        (hash_password(new_password), row["user_id"]),
    )
    revoke_all_sessions(conn, row["user_id"])


def change_password(conn, user_id: str, current_password: str, new_password: str) -> None:
    user = get_user_by_id(conn, user_id)
    if not user or not verify_password(current_password, user["password_hash"]):
        raise AuthError(401, "invalid_credentials", "Current password is incorrect.")
    conn.execute(
        "UPDATE users SET password_hash = %s, updated_at = now() WHERE id = %s",
        (hash_password(new_password), user_id),
    )
    revoke_all_sessions(conn, user_id)


def require_reauthentication(conn, user_id: str, current_password: str | None) -> None:
    """Gate for sensitive account actions (email change, account deletion)
    per docs/02-ACCEPTANCE.md: 'Email changes require verification and
    appropriate reauthentication.' Password accounts must re-present their
    current password. Google-only accounts (no password_hash) have no
    password to re-check in Phase 1 -- this is a known, explicitly tracked
    gap (requiring a fresh Google ID token instead) rather than a silent
    bypass; see the Phase 1 completion report."""
    user = get_user_by_id(conn, user_id)
    if not user:
        raise AuthError(401, "unauthenticated", "Session user no longer exists.")
    if user["password_hash"] is None:
        return  # Google-only account: no password-based reauth available yet.
    if not current_password or not verify_password(current_password, user["password_hash"]):
        raise AuthError(401, "reauth_required", "Confirm your current password to continue.")


# --- Google OAuth -----------------------------------------------------


def login_or_signup_with_google(conn, claims: dict) -> dict:
    """Never implicitly links a Google identity to an existing
    email/password account -- an email collision with no existing
    oauth_accounts row is rejected and must go through the authenticated
    /me/oauth/google/link flow instead (docs/03-TRD.md).

    Returns the same {"session_token"} / {"mfa_required"} shape as
    login_with_password -- an already-linked account with MFA enabled
    still has to clear that second factor, Google sign-in is not a way
    around it."""
    subject = claims["sub"]
    email = claims["email"]

    linked = conn.execute(
        """
        SELECT u.* FROM oauth_accounts o
        JOIN users u ON u.id = o.user_id
        WHERE o.provider = 'google' AND o.provider_subject = %s
        """,
        (subject,),
    ).fetchone()
    if linked:
        if linked["disabled_at"] is not None:
            raise AuthError(403, "account_disabled", "This account is disabled.")

        from app.security.mfa import is_mfa_enabled

        if is_mfa_enabled(conn, str(linked["id"])):
            from app.security.mfa_login import issue_mfa_login_challenge
            return {"mfa_required": True, "mfa_token": issue_mfa_login_challenge(str(linked["id"]))}

        return {"session_token": create_session(conn, linked["id"])}

    existing_email = get_user_by_email(conn, email)
    if existing_email:
        raise AuthError(
            409,
            "account_exists_unlinked",
            "An account with this email already exists. Log in and link Google from account settings.",
        )

    user, _company = _create_user_with_company(conn, email, claims.get("name") or email, password_hash=None)
    conn.execute(
        "INSERT INTO oauth_accounts (user_id, provider, provider_subject) VALUES (%s, 'google', %s)",
        (user["id"], subject),
    )
    conn.execute("UPDATE users SET email_verified_at = now() WHERE id = %s", (user["id"],))
    return {"session_token": create_session(conn, user["id"])}


def link_google_account(conn, user_id: str, claims: dict) -> None:
    subject = claims["sub"]
    existing = conn.execute(
        "SELECT user_id FROM oauth_accounts WHERE provider = 'google' AND provider_subject = %s",
        (subject,),
    ).fetchone()
    if existing:
        raise AuthError(409, "google_already_linked", "This Google account is already linked to another user.")
    conn.execute(
        "INSERT INTO oauth_accounts (user_id, provider, provider_subject) VALUES (%s, 'google', %s)",
        (user_id, subject),
    )


# --- Email change -----------------------------------------------------


def request_email_change(conn, user_id: str, new_email: str, current_password: str | None) -> None:
    require_reauthentication(conn, user_id, current_password)
    normalized = normalize_email(new_email)
    conflict = conn.execute(
        "SELECT id FROM users WHERE normalized_email = %s", (normalized,)
    ).fetchone()
    if conflict:
        raise AuthError(409, "email_in_use", "That email is already in use.")
    token = _create_auth_token(
        conn, user_id, "change_email", VERIFY_EMAIL_TTL_SECONDS, pending_email=new_email
    )
    send_email_change_confirmation(new_email, token)


def confirm_email_change(conn, token: str) -> None:
    row = _consume_auth_token(conn, token, "change_email")
    if not row or not row["pending_email"]:
        raise AuthError(410, "token_invalid", "This link is invalid or has expired.")
    new_email = row["pending_email"]
    conflict = conn.execute(
        "SELECT id FROM users WHERE normalized_email = %s AND id != %s",
        (normalize_email(new_email), row["user_id"]),
    ).fetchone()
    if conflict:
        raise AuthError(409, "email_in_use", "That email is already in use.")
    conn.execute(
        """
        UPDATE users
        SET email = %s, normalized_email = %s, email_verified_at = now(), updated_at = now()
        WHERE id = %s
        """,
        (new_email, normalize_email(new_email), row["user_id"]),
    )


# --- Account deletion ---------------------------------------------------


def delete_account(conn, user_id: str, current_password: str | None) -> str | None:
    """Immediate revocation + tracked async cleanup (docs/15 B3, docs/16
    DELETE /me). Inside this one transaction: every session is revoked, the
    company is soft-deleted, the bot is unpublished and disabled and every
    source is marked deleted -- so no visitor or owner path can reach the
    data from this moment. A `company_cleanup` job then removes vectors and
    hard-deletes tenant rows. Returns that job's id (None if the user had no
    company)."""
    require_reauthentication(conn, user_id, current_password)

    company = conn.execute(
        "SELECT id FROM companies WHERE owner_user_id = %s AND deleted_at IS NULL", (user_id,)
    ).fetchone()

    revoke_all_sessions(conn, user_id)
    conn.execute(
        "UPDATE companies SET deleted_at = now(), updated_at = now() WHERE owner_user_id = %s AND deleted_at IS NULL",
        (user_id,),
    )
    conn.execute(
        "UPDATE users SET disabled_at = now(), updated_at = now() WHERE id = %s",
        (user_id,),
    )
    if not company:
        return None

    company_id = str(company["id"])
    conn.execute(
        "UPDATE bots SET active_publication_id = NULL, disabled_at = now(), updated_at = now() WHERE company_id = %s",
        (company_id,),
    )
    conn.execute(
        "UPDATE documents SET deleted_at = now(), updated_at = now() WHERE company_id = %s AND deleted_at IS NULL",
        (company_id,),
    )
    from app.jobs.queue import enqueue_job

    job_id, _is_new = enqueue_job(conn, company_id, kind="company_cleanup", idempotency_key=f"company_cleanup:{company_id}")
    return job_id
