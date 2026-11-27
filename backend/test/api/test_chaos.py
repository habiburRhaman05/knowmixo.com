"""Chaos tests (D2.7, launch/13-SPRINT-10-DAYS.md Day 2): fault injection
for Postgres and Redis against the REAL managed services this app
actually uses (Neon, Upstash) -- there is no local container to kill, so
failures are injected at the client library boundary instead. That is a
deliberate adaptation of "kill the container mid-request", not a weaker
substitute: it reproduces the exact same failure the app would see
(an OperationalError/ConnectionError raised mid-call), just
deterministically instead of racing a real process kill.

Postgres: a connection that dies partway through a multi-statement
request must roll back EVERYTHING in that transaction (no partial
commit) and the request must answer 503, not a bare 500 or a false
success.

Redis: an outage must degrade the rate limiter to "allow" (fail open --
see app/security/rate_limit.py), never 500 a public/auth path.
"""
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


def test_postgres_dying_mid_signup_rolls_back_everything_and_returns_503(client, db_conn, monkeypatch):
    """Simulates the connection dying between creating the user row and
    creating the company row inside app/auth/service.signup()."""
    email = f"chaos-{uuid.uuid4().hex[:8]}@example.com"
    real_execute = psycopg.Connection.execute

    def _flaky_execute(self, query, params=None, **kwargs):
        if isinstance(query, str) and "INSERT INTO companies" in query:
            raise psycopg.OperationalError("simulated connection failure (chaos test)")
        return real_execute(self, query, params, **kwargs)

    monkeypatch.setattr(psycopg.Connection, "execute", _flaky_execute)

    r = client.post("/api/v1/auth/signup", json={"email": email, "password": "correct-horse-battery", "name": "Chaos"})

    assert r.status_code == 503
    assert r.json()["code"] == "database_unavailable"
    assert "request_id" in r.json()

    monkeypatch.undo()  # restore the real execute before using db_conn to verify
    user = db_conn.execute("SELECT id FROM users WHERE normalized_email = %s", (email,)).fetchone()
    assert user is None, "the user insert must have been rolled back along with the failed company insert"


def test_postgres_dying_mid_signup_does_not_leave_the_connection_pool_broken(client, monkeypatch):
    """A single failed request must not poison the pool for the next one
    -- the pool's own health check (check=ConnectionPool.check_connection,
    app/postgres_resilience.py) and psycopg's rollback-on-exception both
    apply here."""
    real_execute = psycopg.Connection.execute
    call_count = {"n": 0}

    def _fail_once(self, query, params=None, **kwargs):
        if isinstance(query, str) and "INSERT INTO companies" in query and call_count["n"] == 0:
            call_count["n"] += 1
            raise psycopg.OperationalError("simulated connection failure (chaos test)")
        return real_execute(self, query, params, **kwargs)

    monkeypatch.setattr(psycopg.Connection, "execute", _fail_once)

    email_a = f"chaos-{uuid.uuid4().hex[:8]}@example.com"
    email_b = f"chaos-{uuid.uuid4().hex[:8]}@example.com"

    first = client.post("/api/v1/auth/signup", json={"email": email_a, "password": "correct-horse-battery", "name": "A"})
    assert first.status_code == 503

    second = client.post("/api/v1/auth/signup", json={"email": email_b, "password": "correct-horse-battery", "name": "B"})
    assert second.status_code == 202  # the pool recovered -- this is a normal, successful signup


def test_redis_outage_degrades_rate_limiting_to_allow_not_500(monkeypatch):
    """Exercises RateLimited directly (app/security/rate_limit.py) against
    a Redis client that raises on every call, standing in for an Upstash
    outage. Must never raise -- a broken rate limiter fails OPEN."""
    from app.security import rate_limit as rate_limit_module
    from starlette.requests import Request

    class _DownRedis:
        def is_degraded(self):
            raise ConnectionError("simulated Redis outage (chaos test)")

    monkeypatch.setattr(rate_limit_module, "get_redis", lambda: _DownRedis())

    dep = rate_limit_module.RateLimited(1, 60, f"chaos_{uuid.uuid4().hex[:8]}")
    request = Request({"type": "http", "client": ("203.0.113.5", 1234), "headers": [], "method": "GET", "path": "/"})

    for _ in range(5):  # well past any real limit -- must still never block or raise
        dep(request)


def test_redis_outage_during_a_real_rate_limited_request_still_succeeds(client, monkeypatch):
    """End-to-end: POST /api/v1/auth/login (rate-limited) must still
    return its normal response when Redis is down, not a 500 from the
    rate limiter itself.

    test/api/conftest.py stubs RateLimiter.check_limit to always-allow
    for the whole functional suite (see its docstring); that stub would
    make this test pass trivially without ever touching the real
    fail-open code path, so it's restored here just for this test."""
    from app.redis_resilience import RateLimiter
    from app.security import rate_limit as rate_limit_module

    monkeypatch.setattr(RateLimiter, "check_limit", RateLimiter._unpatched_check_limit)

    class _DownRedis:
        def is_degraded(self):
            raise ConnectionError("simulated Redis outage (chaos test)")

    monkeypatch.setattr(rate_limit_module, "get_redis", lambda: _DownRedis())

    r = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong"})
    assert r.status_code == 401  # normal "invalid credentials" -- not a 500 from a broken limiter
