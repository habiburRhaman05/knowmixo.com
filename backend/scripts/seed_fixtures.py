"""Seed one company + one bot + three sources + one visitor session into the
dev DB so eval + e2e + dev UX can proceed without hand-clicking signup.

Idempotent: a second run is a no-op (uses deterministic ids).

Usage:
    python scripts/seed_fixtures.py

Safety: refuses to run if `APP_ENV=production` or the resolved
`DATABASE_URL` host contains `prod` / `.neon.tech` with a `prod` tag.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.db import connection  # noqa: E402

# Stable UUIDs so a second run doesn't duplicate rows.
COMPANY_ID = "11111111-1111-1111-1111-111111111111"
USER_ID = "11111111-1111-1111-1111-111111111112"
BOT_ID = "11111111-1111-1111-1111-111111111113"
DOC_IDS = {
    "returns": "11111111-1111-1111-1111-11111111aa01",
    "shipping": "11111111-1111-1111-1111-11111111aa02",
    "warranty": "11111111-1111-1111-1111-11111111aa03",
}


def _safety_check() -> None:
    s = settings()
    if s.app_env == "production":
        raise SystemExit("[seed] refusing to run against APP_ENV=production")
    # Simple host-based guard; adjust once we have a prod convention.
    if "prod" in (s.database_url or "").lower():
        raise SystemExit("[seed] DATABASE_URL looks production-tagged; refusing")


def _ensure_user(conn) -> None:
    conn.execute(
        """
        INSERT INTO users (id, normalized_email, email, password_hash, name, email_verified_at)
        VALUES (%s, 'demo@acme.example', 'demo@acme.example', NULL, 'Demo Owner', now())
        ON CONFLICT (id) DO NOTHING
        """,
        (USER_ID,),
    )


def _ensure_company(conn) -> None:
    conn.execute(
        """
        INSERT INTO companies (id, owner_user_id, name, website, industry)
        VALUES (%s, %s, 'Acme Demo', 'https://acme.example', 'SaaS')
        ON CONFLICT (id) DO NOTHING
        """,
        (COMPANY_ID, USER_ID),
    )
    conn.execute(
        """
        INSERT INTO memberships (company_id, user_id, role)
        VALUES (%s, %s, 'owner')
        ON CONFLICT (company_id, user_id) DO NOTHING
        """,
        (COMPANY_ID, USER_ID),
    )


def _ensure_bot(conn) -> None:
    conn.execute(
        """
        INSERT INTO bots (id, company_id, public_id, draft_config)
        VALUES (%s, %s, 'pub_demo_acme', %s::jsonb)
        ON CONFLICT (id) DO NOTHING
        """,
        (BOT_ID, COMPANY_ID, json.dumps({"name": "Acme Help", "greeting": "Hi! I quote our docs."})),
    )


def _ensure_sources(conn) -> None:
    for key, doc_id in DOC_IDS.items():
        title = {"returns": "Returns policy", "shipping": "Shipping times", "warranty": "Warranty"}[key]
        body = {
            "returns": "Acme accepts returns within 30 days of delivery for a full refund.",
            "shipping": "Standard US shipping takes 3-5 business days.",
            "warranty": "All Acme electronics include a 12-month manufacturer warranty against defects.",
        }[key]
        conn.execute(
            """
            INSERT INTO documents (id, company_id, bot_id, kind, title)
            VALUES (%s, %s, %s, 'text', %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (doc_id, COMPANY_ID, BOT_ID, title),
        )
        conn.execute(
            """
            INSERT INTO document_versions (document_id, version, status, chunk_count)
            VALUES (%s, 1, 'ready', 1)
            ON CONFLICT (document_id, version) DO NOTHING
            """,
            (doc_id,),
        )
        # Attach a single chunk with text so the eval harness and widget
        # preview have something non-empty.
        version_id = conn.execute(
            "SELECT id FROM document_versions WHERE document_id = %s AND version = 1",
            (doc_id,),
        ).fetchone()["id"]
        conn.execute(
            """
            INSERT INTO chunks (version_id, ordinal, page, heading, text, vector_id)
            VALUES (%s, 0, 1, %s, %s, %s)
            ON CONFLICT (version_id, ordinal) DO NOTHING
            """,
            (version_id, title, body, f"demo:{doc_id}:0"),
        )


def main() -> int:
    _safety_check()
    with connection() as conn:
        _ensure_user(conn)
        _ensure_company(conn)
        _ensure_bot(conn)
        _ensure_sources(conn)

    # One-shot CLI script: close the pool explicitly rather than letting the
    # interpreter garbage-collect it at shutdown. On Python 3.13+,
    # ConnectionPool.__del__ tries to join a background thread during
    # finalization and raises a (harmless but alarming) PythonFinalizationError
    # if we don't close it first ourselves.
    from app.postgres_resilience import reset_pg

    reset_pg()

    print("[seed] ok — demo workspace is ready")
    print(f"  company_id = {COMPANY_ID}")
    print(f"  user email = demo@acme.example")
    print(f"  bot public_id = pub_demo_acme")
    return 0


if __name__ == "__main__":
    sys.exit(main())
