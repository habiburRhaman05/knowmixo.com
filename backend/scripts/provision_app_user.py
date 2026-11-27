"""One-time, per-environment provisioning for the `app_user` Postgres role
(ADR 002 / migration 0011).

This is deliberately NOT part of the Alembic migration: the migration
creates the role and its grants identically in every environment (that's
schema, safe to version-control and replay); the PASSWORD is a secret,
must be unique per environment, and must never appear in a migration
script, a log line, or this script's own stdout.

What this does:
  1. Generates a fresh random password with `secrets.token_urlsafe`.
  2. Runs `ALTER ROLE app_user PASSWORD %s` via a parameterized query
     (psycopg handles quoting -- the password is never interpolated into
     SQL text).
  3. Builds `DATABASE_URL_APP` from the current `DATABASE_URL`'s host /
     port / dbname / query string, swapping only the user and password.
  4. Writes (or updates) the `DATABASE_URL_APP=` line in `backend/.env`.
     The password is never printed to stdout, logged, or returned by this
     script in any form.

Safe to re-run: by default it refuses to rotate an existing
DATABASE_URL_APP (to avoid silently invalidating a value already deployed
elsewhere). Pass --rotate to intentionally generate and deploy a new one.

Usage:
    python scripts/provision_app_user.py           # first-time setup
    python scripts/provision_app_user.py --rotate  # intentional rotation
"""
from __future__ import annotations

import argparse
import re
import secrets
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.config import settings  # noqa: E402
from app.db import connection  # noqa: E402

ENV_PATH = ROOT / ".env"
ENV_VAR_NAME = "DATABASE_URL_APP"


def _build_app_user_url(admin_url: str, password: str) -> str:
    """`username`/`password` are read-only derived properties on
    `ParseResult`, not real named-tuple fields -- `_replace()` only
    accepts `netloc` (and the other real fields), so the new
    user:pass@host:port must be assembled into `netloc` directly."""
    parsed = urlparse(admin_url)
    netloc = f"app_user:{password}@{parsed.hostname}"
    if parsed.port:
        netloc += f":{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc))


def _existing_env_has_var(name: str) -> bool:
    if not ENV_PATH.exists():
        return False
    pattern = re.compile(rf"^{re.escape(name)}\s*=", re.MULTILINE)
    return bool(pattern.search(ENV_PATH.read_text(encoding="utf-8-sig")))


def _write_env_var(name: str, value: str) -> None:
    """Appends or replaces one `NAME=value` line. Never logs `value`."""
    text = ENV_PATH.read_text(encoding="utf-8-sig") if ENV_PATH.exists() else ""
    pattern = re.compile(rf"^{re.escape(name)}\s*=.*$", re.MULTILINE)
    line = f"{name}={value}"
    if pattern.search(text):
        text = pattern.sub(line, text)
    else:
        if text and not text.endswith("\n"):
            text += "\n"
        text += line + "\n"
    ENV_PATH.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rotate",
        action="store_true",
        help="Generate and deploy a NEW password even if DATABASE_URL_APP already exists.",
    )
    args = parser.parse_args()

    if _existing_env_has_var(ENV_VAR_NAME) and not args.rotate:
        print(
            f"[provision] {ENV_VAR_NAME} already set in {ENV_PATH}. "
            "Refusing to overwrite without --rotate."
        )
        return 0

    s = settings()
    if not s.database_url:
        print("[provision] DATABASE_URL is not set; nothing to provision against.")
        return 1

    password = secrets.token_urlsafe(32)

    with connection() as conn:
        row = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'app_user'").fetchone()
        if not row:
            print(
                "[provision] Role 'app_user' does not exist yet. "
                "Run `alembic upgrade head` (migration 0011) first."
            )
            return 1
        # `ALTER ROLE ... PASSWORD` is DDL-shaped and does not accept bind
        # parameters (confirmed: Postgres raises a syntax error on `$1`
        # here). psycopg.sql.Literal safely quotes/escapes the value for
        # inclusion in the statement text -- this is NOT raw string
        # interpolation, it goes through the same quoting psycopg uses
        # for any literal, so it remains injection-safe even though the
        # statement itself can't be parameterized the normal way.
        from psycopg import sql

        conn.execute(sql.SQL("ALTER ROLE app_user PASSWORD {}").format(sql.Literal(password)))
        conn.commit()

    app_url = _build_app_user_url(s.database_url, password)
    _write_env_var(ENV_VAR_NAME, app_url)

    from app.postgres_resilience import reset_pg

    reset_pg()

    print(f"[provision] app_user password {'rotated' if args.rotate else 'set'}.")
    print(f"[provision] {ENV_VAR_NAME} written to {ENV_PATH} (value not shown).")
    print(
        "[provision] Next: the application's request-serving pool needs an "
        "explicit audit of bootstrap/admin code paths (signup, account "
        "cleanup, webhook ingestion, crawl worker) before it can safely "
        "switch from the owner role to app_user. See migration 0011's "
        "docstring and launch/DAY-2-REPORT.md."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
