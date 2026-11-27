"""MFA: TOTP setup/verify + recovery codes + step-up tokens (D8.5).
From-scratch design: no spec exists beyond "MFA (TOTP) for owners" +
"add pyotp + backup codes" (launch/01-FEATURE-INVENTORY.md K.4).

Flow:
  1. setup_totp() generates a secret, stores it ENCRYPTED but unconfirmed
     (mfa_enabled_at stays NULL), returns a provisioning URI for the
     owner's authenticator app to scan.
  2. confirm_totp(code) proves possession of a real code from that
     secret before flipping mfa_enabled_at -- a secret nobody has
     confirmed must never be treated as an active factor.
  3. verify_totp(code) / verify_recovery_code(code) are used at login
     step-up and before destructive actions.
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone

import pyotp

from app.security.encryption import EncryptionNotConfigured, decrypt, encrypt
from app.security.passwords import hash_password, verify_password
from app.security.tokens import generate_opaque_token, hash_token

log = logging.getLogger(__name__)

RECOVERY_CODE_COUNT = 10
STEP_UP_TTL_SECONDS = 10 * 60  # 10 minutes -- matches the common "step-up" freshness window


class MFAError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _issuer() -> str:
    return "Knowmivo"


def setup_totp(conn, user_id: str, account_email: str) -> dict:
    """Generates and stores (encrypted, unconfirmed) a new TOTP secret.
    Calling this again before confirm_totp overwrites the pending secret --
    safe, since nothing has been confirmed yet."""
    try:
        secret = pyotp.random_base32()
        encrypted = encrypt(secret)
    except EncryptionNotConfigured as exc:
        raise MFAError(503, "mfa_not_configured", "MFA is not available right now.") from exc

    conn.execute(
        "UPDATE users SET mfa_secret = %s, mfa_enabled_at = NULL WHERE id = %s",
        (encrypted, user_id),
    )
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=account_email, issuer_name=_issuer())
    return {"secret": secret, "provisioning_uri": uri}


def _generate_recovery_codes() -> list[str]:
    return [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(RECOVERY_CODE_COUNT)]


def confirm_totp(conn, user_id: str, code: str) -> list[str]:
    """Verifies the first real code, activates MFA, and issues a fresh set
    of recovery codes (any prior unused ones are invalidated -- a second
    'confirm' should not silently keep old codes alive alongside new ones)."""
    row = conn.execute("SELECT mfa_secret FROM users WHERE id = %s", (user_id,)).fetchone()
    if not row or not row["mfa_secret"]:
        raise MFAError(400, "mfa_setup_not_started", "Call MFA setup before confirming.")

    secret = decrypt(row["mfa_secret"])
    if not pyotp.TOTP(secret).verify(code, valid_window=1):
        raise MFAError(400, "invalid_code", "Invalid authenticator code.")

    conn.execute("UPDATE users SET mfa_enabled_at = now() WHERE id = %s", (user_id,))
    conn.execute("DELETE FROM mfa_recovery_codes WHERE user_id = %s", (user_id,))

    plain_codes = _generate_recovery_codes()
    for plain in plain_codes:
        conn.execute(
            "INSERT INTO mfa_recovery_codes (user_id, code_hash) VALUES (%s, %s)",
            (user_id, hash_password(plain)),
        )
    return plain_codes


def disable_mfa(conn, user_id: str) -> None:
    conn.execute("UPDATE users SET mfa_secret = NULL, mfa_enabled_at = NULL WHERE id = %s", (user_id,))
    conn.execute("DELETE FROM mfa_recovery_codes WHERE user_id = %s", (user_id,))


def is_mfa_enabled(conn, user_id: str) -> bool:
    row = conn.execute("SELECT mfa_enabled_at FROM users WHERE id = %s", (user_id,)).fetchone()
    return bool(row and row["mfa_enabled_at"])


def verify_totp(conn, user_id: str, code: str) -> bool:
    row = conn.execute(
        "SELECT mfa_secret FROM users WHERE id = %s AND mfa_enabled_at IS NOT NULL", (user_id,)
    ).fetchone()
    if not row or not row["mfa_secret"]:
        return False
    secret = decrypt(row["mfa_secret"])
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def verify_recovery_code(conn, user_id: str, code: str) -> bool:
    """Single-use: the matching row is marked used_at in the same
    statement that validates it, so a code cannot be replayed under a
    race. Hashed with the same Argon2id helper as passwords -- these are
    low-entropy-ish human-typed secrets, not raw bearer tokens, so a
    slow hash is the right primitive, not SHA-256."""
    rows = conn.execute(
        "SELECT id, code_hash FROM mfa_recovery_codes WHERE user_id = %s AND used_at IS NULL",
        (user_id,),
    ).fetchall()
    for row in rows:
        if verify_password(code, row["code_hash"]):
            result = conn.execute(
                "UPDATE mfa_recovery_codes SET used_at = now() WHERE id = %s AND used_at IS NULL",
                (row["id"],),
            )
            return result.rowcount > 0
    return False


# --- Step-up tokens (short-lived proof of recent MFA verification) --------


def issue_step_up_token(conn, user_id: str) -> str:
    token = generate_opaque_token()
    expires = datetime.now(timezone.utc) + timedelta(seconds=STEP_UP_TTL_SECONDS)
    conn.execute(
        "INSERT INTO mfa_step_up_tokens (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
        (user_id, hash_token(token), expires),
    )
    return token


def consume_step_up_token(conn, user_id: str, token: str) -> bool:
    result = conn.execute(
        """
        UPDATE mfa_step_up_tokens SET consumed_at = now()
        WHERE user_id = %s AND token_hash = %s AND consumed_at IS NULL AND expires_at > now()
        """,
        (user_id, hash_token(token)),
    )
    return result.rowcount > 0
