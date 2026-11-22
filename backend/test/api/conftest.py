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


@pytest.fixture()
def db_conn(test_database_url, monkeypatch):
    # Point the app's settings at the isolated test database for this test.
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    from app.config import settings

    settings.cache_clear()
    import app.db as db_module

    db_module._pool = None  # force a fresh pool bound to the test database

    with db_module.connection() as conn:
        yield conn
        conn.rollback()  # never leave fixture data committed between tests
