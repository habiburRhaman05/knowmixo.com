"""Isolated-Postgres API test fixtures (docs/10-TEST-AND-LAUNCH.md).

These tests only run against a real database when TEST_DATABASE_URL is
explicitly set -- per docs/11-AGENT-RULES.md rule 6 ("no default live
external API calls in tests"), they must never fire against production or
require network access by default. Point TEST_DATABASE_URL at a disposable
database (e.g. a local Postgres, or a throwaway Neon branch) before running
this suite, and run `alembic upgrade head` against it first.
"""
import os

import pytest


@pytest.fixture(scope="session")
def test_database_url():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set -- skipping isolated-DB API tests")
    return url


@pytest.fixture(scope="session", autouse=True)
def _bind_app_to_test_database(test_database_url, monkeypatch_session):
    """Points the app's connection pool at the test database exactly
    once per session. A previous version of this fixture rebuilt the
    pool per-test without ever closing the old one -- each ConnectionPool
    opens real connections against Neon that are never released, which
    silently exhausts the free-tier connection limit a few tests in and
    makes every subsequent connection attempt hang waiting for a slot
    (looks like a freeze, not an error). One pool for the whole session
    avoids that leak entirely."""
    monkeypatch_session.setenv("DATABASE_URL", test_database_url)
    from app.config import settings

    settings.cache_clear()

    import app.db as db_module

    db_module._pool = None  # built once, lazily, on first get_pool() call below
    from app.postgres_resilience import reset_pg

    reset_pg()  # connection() goes through the resilience pool; rebind it too

    # Never let a test send a real email. If real SMTP credentials happen
    # to be present in the environment (e.g. a shared .env), signup/
    # forgot-password/email-change calls would otherwise open a real
    # smtplib.SMTP_SSL connection to Gmail per test -- slow, rate-limit
    # risk, and (smtplib sets no default socket timeout) an occasional
    # real hang that looks like a frozen test run. Tests that need a raw
    # token read it directly via app.auth.service internals instead of
    # parsing an email, so this no-op is safe everywhere.
    import app.email as email_module

    monkeypatch_session.setattr(email_module, "send_email", lambda to, subject, body: None)

    yield

    if db_module._pool is not None:
        db_module._pool.close()
        db_module._pool = None


@pytest.fixture(scope="session")
def monkeypatch_session():
    """pytest's built-in `monkeypatch` is function-scoped; this session-
    scoped equivalent lets the DATABASE_URL env patch live for the whole
    test session instead of being undone after the first test."""
    mp = pytest.MonkeyPatch()
    yield mp
    mp.undo()


@pytest.fixture()
def db_conn():
    import app.db as db_module

    with db_module.connection() as conn:
        yield conn
        conn.rollback()  # never leave fixture data committed between tests
