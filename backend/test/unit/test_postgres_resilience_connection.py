"""Regression for a Day-1-verification finding: `PostgresResilience.connection()`
retried the caller's own business-logic exceptions whenever their message
happened to contain a word like "connection" or "timeout", and did so by
looping back to `yield` a second time from the same generator -- illegal
per the generator-context-manager protocol, and it raised an opaque
`RuntimeError: generator didn't stop after throw()` that completely masked
the real exception (observed here via a real signup -> SMTP failure).

See launch/DAY-1-REPORT.md (verification addendum) for the live repro.
"""
from __future__ import annotations

import pytest

from app.postgres_resilience import PostgresResilience


class _FakeConn:
    def __init__(self):
        self.closed = False


class _FakePoolConnectionCM:
    """Mimics psycopg_pool's `pool.connection()` context manager."""

    def __init__(self, conn, acquire_error=None):
        self._conn = conn
        self._acquire_error = acquire_error
        self.exits_seen = []

    def __enter__(self):
        if self._acquire_error is not None:
            raise self._acquire_error
        return self._conn

    def __exit__(self, exc_type, exc, tb):
        self.exits_seen.append((exc_type, exc, tb))
        return False  # never suppress


class _FakePool:
    def __init__(self, cms):
        self._cms = list(cms)
        self.calls = 0

    def connection(self):
        cm = self._cms[min(self.calls, len(self._cms) - 1)]
        self.calls += 1
        return cm


def _make_resilience(cms) -> PostgresResilience:
    pg = PostgresResilience.__new__(PostgresResilience)  # bypass __init__ (no real pool)
    pg._pool = _FakePool(cms)
    pg._healthy = True
    pg._last_health_check = 0.0
    return pg


def test_caller_exception_propagates_exactly_once_even_if_message_says_connection():
    """This is the exact crash scenario: the caller's own code raises
    (e.g. an SMTP error whose message contains the word "connection").
    Before the fix this triggered a retry loop that tried to yield twice
    and masked the real error behind RuntimeError. After the fix it must
    propagate the ORIGINAL exception, unchanged, on the first attempt."""
    conn = _FakeConn()
    cm = _FakePoolConnectionCM(conn)
    pg = _make_resilience([cm])

    class FakeSmtpError(Exception):
        pass

    with pytest.raises(FakeSmtpError, match="Connection unexpectedly closed"):
        with pg.connection() as c:
            assert c is conn
            raise FakeSmtpError("Connection unexpectedly closed")

    # Must have attempted exactly one connection acquisition -- no retry.
    assert pg.pool.calls == 1
    assert len(cm.exits_seen) == 1


def test_unrelated_application_error_is_never_retried():
    conn = _FakeConn()
    cm = _FakePoolConnectionCM(conn)
    pg = _make_resilience([cm])

    with pytest.raises(ValueError, match="bad email"):
        with pg.connection() as c:
            raise ValueError("bad email")

    assert pg.pool.calls == 1


def test_successful_use_commits_cleanly():
    conn = _FakeConn()
    cm = _FakePoolConnectionCM(conn)
    pg = _make_resilience([cm])

    with pg.connection() as c:
        assert c is conn

    assert pg.pool.calls == 1
    assert cm.exits_seen == [(None, None, None)]


def test_connection_acquisition_failure_retries_then_succeeds(monkeypatch):
    """A genuine failure to ACQUIRE a connection (pool exhausted, network
    blip) should still retry -- that's the one case retrying is correct."""
    import psycopg

    conn = _FakeConn()
    failing_cm = _FakePoolConnectionCM(None, acquire_error=psycopg.OperationalError("could not connect"))
    ok_cm = _FakePoolConnectionCM(conn)
    fake_pool = _FakePool([failing_cm, ok_cm])
    pg = _make_resilience([])
    pg._pool = fake_pool

    import app.postgres_resilience as pr_module

    monkeypatch.setattr(pr_module.time, "sleep", lambda _s: None)
    # The implementation does `self._pool = None` on a transient failure to
    # force a fresh pool on the next attempt; keep that "fresh" pool as our
    # same fake rather than letting it build a real network connection.
    monkeypatch.setattr(PostgresResilience, "_create_pool", lambda self: fake_pool)

    with pg.connection() as c:
        assert c is conn

    assert fake_pool.calls == 2


def test_connection_acquisition_failure_never_retries_non_transient():
    pg = _make_resilience([_FakePoolConnectionCM(None, acquire_error=ValueError("not a db error"))])

    with pytest.raises(ValueError, match="not a db error"):
        with pg.connection():
            pass  # pragma: no cover -- should never reach the body

    assert pg.pool.calls == 1


def test_is_transient_error_never_matches_non_psycopg_exceptions():
    pg = _make_resilience([])
    # These all contain "transient-looking" substrings but are NOT
    # database errors and must never be classified as transient.
    assert pg._is_transient_error(Exception("Connection unexpectedly closed")) is False
    assert pg._is_transient_error(ValueError("request timeout waiting for user input")) is False
    assert pg._is_transient_error(RuntimeError("broken pipe in unrelated subprocess")) is False


def test_is_transient_error_still_matches_real_psycopg_errors():
    import psycopg

    pg = _make_resilience([])
    assert pg._is_transient_error(psycopg.OperationalError("server closed the connection unexpectedly")) is True
