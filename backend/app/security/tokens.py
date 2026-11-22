import hashlib
import secrets
from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def generate_opaque_token() -> str:
    """A random, unguessable, URL-safe token. Only its hash is ever stored."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """One-way hash for storage. Tokens are bearer secrets -- never store
    them in plaintext (sessions.token_hash / auth_tokens.token_hash)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def expires_at(seconds: int) -> datetime:
    return utcnow() + timedelta(seconds=seconds)


# Short-lived purposes, distinct from session lifetime.
VERIFY_EMAIL_TTL_SECONDS = 60 * 60 * 24  # 24h
RESET_PASSWORD_TTL_SECONDS = 60 * 60  # 1h
CHANGE_EMAIL_TTL_SECONDS = 60 * 60 * 24  # 24h
