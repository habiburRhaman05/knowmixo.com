"""Idempotency-Key support for owner mutations (docs/16-API-ROUTES.md
"Cross-cutting conventions"): a replay with the same key returns the
ORIGINAL result and never repeats the side effect; the same key with a
different request body is a 409, not a silent second execution.

The advisory lock serialises concurrent requests carrying the same key, and
the stored response row is written in the same transaction as the side
effect, so "effect happened but key not recorded" cannot occur.
"""
import hashlib
import json
from typing import Callable

from app.bots.service import BotError

MAX_KEY_LENGTH = 200


def fingerprint(payload) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def run_idempotent(conn, company_id: str, scope: str, key: str | None, payload, action: Callable[[], dict], status_code: int = 200) -> tuple[dict, bool]:
    """Returns (response, replayed). `action` runs at most once per key."""
    if not key:
        return action(), False
    if len(key) > MAX_KEY_LENGTH:
        raise BotError(422, "invalid_idempotency_key", "Idempotency-Key is too long.")

    fp = fingerprint(payload)
    conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"{company_id}:{scope}:{key}",))
    existing = conn.execute(
        "SELECT request_fingerprint, response FROM idempotency_keys WHERE company_id = %s AND scope = %s AND key = %s",
        (company_id, scope, key),
    ).fetchone()
    if existing:
        if existing["request_fingerprint"] != fp:
            raise BotError(409, "idempotency_key_reuse", "This Idempotency-Key was already used with a different request.")
        return existing["response"], True

    response = action()
    conn.execute(
        """
        INSERT INTO idempotency_keys (company_id, scope, key, request_fingerprint, status_code, response)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        """,
        (company_id, scope, key, fp, status_code, json.dumps(response, default=str)),
    )
    return response, False
