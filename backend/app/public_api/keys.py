"""API key management (D9.4, ADR 007). Owner-facing CRUD under
/api/v1/api-keys (NOT /api/v1/public-api/* -- that prefix is for the
keys themselves to call, not for managing them)."""
import json
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.db import connection

_hasher = PasswordHasher()
KEY_PREFIX = "km_live"
ALL_SCOPES = {"conversations:read", "conversations:write", "leads:read", "sources:write", "events:webhook"}


def create_key(company_id: str, created_by: str, name: str, scopes: list[str]) -> dict:
    invalid = set(scopes) - ALL_SCOPES
    if invalid:
        raise ValueError(f"unknown scopes: {sorted(invalid)}")

    prefix = secrets.token_hex(4)
    secret = secrets.token_urlsafe(32)
    hashed = _hasher.hash(secret)
    raw_key = f"{KEY_PREFIX}_{prefix}_{secret}"

    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO api_keys (company_id, name, prefix, hashed, scopes, created_by)
            VALUES (%s, %s, %s, %s, %s::jsonb, %s)
            RETURNING id, name, prefix, scopes, created_at
            """,
            (company_id, name, prefix, hashed, json.dumps(scopes), created_by),
        ).fetchone()

    return {**dict(row), "id": str(row["id"]), "api_key": raw_key}


def list_keys(company_id: str) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT id, name, prefix, scopes, last_used_at, revoked_at, created_at
            FROM api_keys WHERE company_id = %s ORDER BY created_at DESC
            """,
            (company_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def revoke_key(company_id: str, key_id: str) -> bool:
    with connection() as conn:
        result = conn.execute(
            "UPDATE api_keys SET revoked_at = now() WHERE id = %s AND company_id = %s AND revoked_at IS NULL",
            (key_id, company_id),
        )
        return result.rowcount > 0


class ApiKeyPrincipal:
    def __init__(self, key_id: str, company_id: str, scopes: list[str]):
        self.key_id = key_id
        self.company_id = company_id
        self.scopes = set(scopes)

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


def resolve_api_key(bearer_token: str) -> ApiKeyPrincipal | None:
    """Parses `km_live_{prefix}_{secret}`, looks up by prefix (cheap,
    indexed, unique), then Argon2-verifies the secret against the stored
    hash -- the slow hash only ever runs once per request, against the
    single candidate row the prefix narrowed to, never a full-table scan."""
    if not bearer_token.startswith(f"{KEY_PREFIX}_"):
        return None
    rest = bearer_token[len(KEY_PREFIX) + 1:]
    parts = rest.split("_", 1)
    if len(parts) != 2:
        return None
    prefix, secret = parts

    with connection() as conn:
        row = conn.execute(
            "SELECT id, company_id, hashed, scopes FROM api_keys WHERE prefix = %s AND revoked_at IS NULL",
            (prefix,),
        ).fetchone()
        if not row:
            return None
        try:
            _hasher.verify(row["hashed"], secret)
        except (VerifyMismatchError, InvalidHashError):
            return None

        conn.execute("UPDATE api_keys SET last_used_at = now() WHERE id = %s", (row["id"],))

    return ApiKeyPrincipal(str(row["id"]), str(row["company_id"]), row["scopes"] or [])
