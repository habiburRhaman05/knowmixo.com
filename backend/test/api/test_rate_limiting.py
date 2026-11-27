"""Verifies app/security/rate_limit.py against the real Redis instance
(docs/03-RISKS-AND-BLOCKERS.md §2.8). The functional API suite stubs
RateLimiter.check_limit to always-allow (test/api/conftest.py) because
TestClient reuses one fake client address for every request in the
session -- this file is where rate-limiting itself is actually proven,
against the real backend, not a mock.

Requires REDIS_URL to be a real, reachable Redis (same one the app uses
in dev). Skipped if unreachable, same policy as the DB-backed suite.
"""
import time
import uuid

import pytest
from starlette.requests import Request

from app.redis_resilience import get_redis, reset_redis
from app.security.rate_limit import RateLimited


def _fake_request(ip: str) -> Request:
    scope = {
        "type": "http",
        "client": (ip, 12345),
        "headers": [],
        "method": "GET",
        "path": "/",
    }
    return Request(scope)


@pytest.fixture(autouse=True)
def _real_redis_or_skip(monkeypatch):
    from app.redis_resilience import RateLimiter

    # The session-wide suite stubs RateLimiter.check_limit to always-allow
    # (test/api/conftest.py) so ~200 unrelated functional tests don't share
    # one rate-limit bucket under TestClient's fixed fake IP. Restore the
    # real implementation for just this file's tests.
    monkeypatch.setattr(RateLimiter, "check_limit", RateLimiter._unpatched_check_limit)

    reset_redis()
    redis = get_redis()
    if not redis.ping():
        pytest.skip("Redis is not reachable -- cannot test real rate-limiting behavior")
    yield
    reset_redis()


def test_allows_up_to_the_limit_then_blocks():
    dep = RateLimited(3, 60, f"test_{uuid.uuid4().hex[:8]}")
    ip = f"203.0.113.{uuid.uuid4().int % 255}"

    dep(_fake_request(ip))
    dep(_fake_request(ip))
    dep(_fake_request(ip))  # 3rd request still within the limit of 3

    with pytest.raises(Exception) as exc_info:
        dep(_fake_request(ip))  # 4th request exceeds the limit
    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["code"] == "rate_limited"


def test_different_ips_do_not_share_a_bucket():
    dep = RateLimited(1, 60, f"test_{uuid.uuid4().hex[:8]}")
    ip_a = f"203.0.113.{uuid.uuid4().int % 255}"
    ip_b = f"203.0.113.{(uuid.uuid4().int + 1) % 255}"

    dep(_fake_request(ip_a))  # uses up A's one allowed request
    dep(_fake_request(ip_b))  # B is unaffected -- separate bucket


def test_different_key_prefixes_do_not_share_a_bucket():
    ip = f"203.0.113.{uuid.uuid4().int % 255}"
    dep_signup = RateLimited(1, 60, f"test_signup_{uuid.uuid4().hex[:8]}")
    dep_login = RateLimited(1, 60, f"test_login_{uuid.uuid4().hex[:8]}")

    dep_signup(_fake_request(ip))
    dep_login(_fake_request(ip))  # different route -- must not be blocked by signup's bucket


def test_window_expiry_allows_requests_again():
    dep = RateLimited(1, 1, f"test_{uuid.uuid4().hex[:8]}")  # 1-second window
    ip = f"203.0.113.{uuid.uuid4().int % 255}"

    dep(_fake_request(ip))
    with pytest.raises(Exception):
        dep(_fake_request(ip))

    time.sleep(1.1)
    dep(_fake_request(ip))  # window has rolled over -- allowed again


def test_fails_open_when_redis_is_unreachable(monkeypatch):
    from app.security import rate_limit as rate_limit_module

    class _AlwaysBrokenRedis:
        def is_degraded(self):
            raise RuntimeError("simulated redis outage")

    monkeypatch.setattr(rate_limit_module, "get_redis", lambda: _AlwaysBrokenRedis())
    dep = RateLimited(1, 60, f"test_{uuid.uuid4().hex[:8]}")
    ip = f"203.0.113.{uuid.uuid4().int % 255}"

    # Must not raise, and must not 500 -- a broken rate limiter degrades to
    # "allow", never to blocking (or crashing) a public/auth path.
    dep(_fake_request(ip))
    dep(_fake_request(ip))
    dep(_fake_request(ip))
