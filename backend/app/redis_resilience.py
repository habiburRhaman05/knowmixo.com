"""Redis resilience layer for Phase 8 hardening.

Provides circuit breaker, retry logic, and graceful degradation for Redis
outages. All Redis-dependent features (rate limiting, caching, session store)
must use this wrapper instead of raw redis client.
"""
import logging
import os
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

import redis
from redis.exceptions import ConnectionError, RedisError, TimeoutError

log = logging.getLogger(__name__)

# Configuration
REDIS_MAX_RETRIES = int(os.environ.get("REDIS_MAX_RETRIES", "3"))
REDIS_RETRY_BASE_DELAY = float(os.environ.get("REDIS_RETRY_BASE_DELAY", "0.1"))
REDIS_RETRY_MAX_DELAY = float(os.environ.get("REDIS_RETRY_MAX_DELAY", "2.0"))
REDIS_CIRCUIT_BREAKER_THRESHOLD = int(os.environ.get("REDIS_CIRCUIT_BREAKER_THRESHOLD", "5"))
REDIS_CIRCUIT_BREAKER_TIMEOUT = float(os.environ.get("REDIS_CIRCUIT_BREAKER_TIMEOUT", "30.0"))
REDIS_SOCKET_TIMEOUT = float(os.environ.get("REDIS_SOCKET_TIMEOUT", "5.0"))
REDIS_SOCKET_CONNECT_TIMEOUT = float(os.environ.get("REDIS_SOCKET_CONNECT_TIMEOUT", "5.0"))

T = TypeVar("T")


class CircuitBreaker:
    """Simple circuit breaker for Redis connections."""

    def __init__(self, threshold: int = REDIS_CIRCUIT_BREAKER_THRESHOLD, timeout: float = REDIS_CIRCUIT_BREAKER_TIMEOUT):
        self.failure_count = 0
        self.threshold = threshold
        self.timeout = timeout
        self.last_failure_time: Optional[float] = None
        self.state = "closed"  # closed, open, half-open

    def record_success(self):
        self.failure_count = 0
        self.state = "closed"

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.threshold:
            self.state = "open"
            log.warning(f"Redis circuit breaker opened after {self.failure_count} failures")

    def can_execute(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if self.last_failure_time and (time.time() - self.last_failure_time) >= self.timeout:
                self.state = "half-open"
                log.info("Redis circuit breaker entering half-open state")
                return True
            return False
        # half-open: allow one request through
        return True


class ResilientRedis:
    """Redis client wrapper with retry, circuit breaker, and graceful degradation."""

    def __init__(self, url: Optional[str] = None):
        # Prefer explicit arg, then settings() (which reads .env via
        # pydantic_settings and strips quotes), then os.environ as a last
        # resort. Previously only os.environ was consulted which meant the
        # value loaded from .env by the backend was invisible to the Redis
        # layer — breaking rate limits / sessions in prod. See
        # launch/00-BUILD-HEALTH.md §2.1.
        if url is None:
            try:
                from app.config import settings

                url = settings().redis_url
            except Exception:  # noqa: BLE001 — avoid import-cycle surprises
                url = os.environ.get("REDIS_URL", "")
        self.url = url or ""
        if not self.url:
            raise ValueError("REDIS_URL is required")

        self._client: Optional[redis.Redis] = None
        self._circuit_breaker = CircuitBreaker()
        self._degraded_mode = False

    def _get_client(self) -> redis.Redis:
        if self._client is None:
            self._client = redis.from_url(
                self.url,
                socket_timeout=REDIS_SOCKET_TIMEOUT,
                socket_connect_timeout=REDIS_SOCKET_CONNECT_TIMEOUT,
                socket_keepalive=True,
                retry_on_timeout=True,
                health_check_interval=30,
                decode_responses=True,
            )
        return self._client

    def _execute_with_retry(self, operation: Callable[..., T], *args, **kwargs) -> T:
        """Execute a Redis operation with retry logic and circuit breaker."""
        if not self._circuit_breaker.can_execute():
            if not self._degraded_mode:
                log.error("Redis circuit breaker open - entering degraded mode")
                self._degraded_mode = True
            raise RedisError("Redis unavailable (circuit breaker open)")

        last_exception = None
        for attempt in range(REDIS_MAX_RETRIES):
            try:
                client = self._get_client()
                result = operation(client, *args, **kwargs)
                self._circuit_breaker.record_success()
                if self._degraded_mode:
                    log.info("Redis recovered - exiting degraded mode")
                    self._degraded_mode = False
                return result
            except (ConnectionError, TimeoutError) as e:
                last_exception = e
                self._circuit_breaker.record_failure()
                if attempt < REDIS_MAX_RETRIES - 1:
                    delay = min(
                        REDIS_RETRY_BASE_DELAY * (2 ** attempt),
                        REDIS_RETRY_MAX_DELAY,
                    )
                    log.warning(f"Redis operation failed (attempt {attempt + 1}/{REDIS_MAX_RETRIES}), retrying in {delay}s: {e}")
                    time.sleep(delay)
                else:
                    log.error(f"Redis operation failed after {REDIS_MAX_RETRIES} attempts: {e}")
            except RedisError as e:
                # Non-retryable Redis error
                self._circuit_breaker.record_failure()
                log.error(f"Redis non-retryable error: {e}")
                raise

        raise last_exception or RedisError("Redis operation failed")

    # Graceful degradation helpers
    def is_degraded(self) -> bool:
        return self._degraded_mode

    def force_degraded(self, degraded: bool = True):
        self._degraded_mode = degraded
        if degraded:
            log.warning("Redis forced into degraded mode")

    # Core operations with resilience
    def get(self, key: str) -> Optional[str]:
        if self._degraded_mode:
            return None
        return self._execute_with_retry(lambda c, k: c.get(k), key)

    def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        if self._degraded_mode:
            return False
        return self._execute_with_retry(lambda c, k, v, ex: c.set(k, v, ex=ex), key, value, ex)

    def setex(self, key: str, seconds: int, value: str) -> bool:
        if self._degraded_mode:
            return False
        return self._execute_with_retry(lambda c, k, s, v: c.setex(k, s, v), key, seconds, value)

    def delete(self, *keys: str) -> int:
        if self._degraded_mode:
            return 0
        return self._execute_with_retry(lambda c, k: c.delete(*k), keys)

    def exists(self, *keys: str) -> int:
        if self._degraded_mode:
            return 0
        return self._execute_with_retry(lambda c, k: c.exists(*k), keys)

    def incr(self, key: str) -> int:
        if self._degraded_mode:
            return 0
        return self._execute_with_retry(lambda c, k: c.incr(k), key)

    def expire(self, key: str, seconds: int) -> bool:
        if self._degraded_mode:
            return False
        return self._execute_with_retry(lambda c, k, s: c.expire(k, s), key, seconds)

    def ttl(self, key: str) -> int:
        if self._degraded_mode:
            return -2
        return self._execute_with_retry(lambda c, k: c.ttl(k), key)

    def eval(self, script: str, num_keys: int, *keys_and_args) -> Any:
        if self._degraded_mode:
            return None
        return self._execute_with_retry(lambda c, s, n, k: c.eval(s, n, *k), script, num_keys, keys_and_args)

    def evalsha(self, sha: str, num_keys: int, *keys_and_args) -> Any:
        if self._degraded_mode:
            return None
        return self._execute_with_retry(lambda c, s, n, k: c.evalsha(s, n, *k), sha, num_keys, keys_and_args)

    def script_load(self, script: str) -> str:
        if self._degraded_mode:
            return ""
        return self._execute_with_retry(lambda c, s: c.script_load(s), script)

    def ping(self) -> bool:
        try:
            return self._execute_with_retry(lambda c: c.ping())
        except RedisError:
            return False


# Global instance
_redis_client: Optional[ResilientRedis] = None


def get_redis() -> ResilientRedis:
    """Get or create the global resilient Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = ResilientRedis()
    return _redis_client


def reset_redis():
    """Reset the global Redis client (for testing)."""
    global _redis_client
    _redis_client = None


@contextmanager
def redis_session():
    """Context manager for Redis operations with automatic degradation handling."""
    client = get_redis()
    try:
        yield client
    except RedisError as e:
        log.warning(f"Redis session error, continuing in degraded mode: {e}")
        client.force_degraded(True)
        yield client


def with_redis_fallback(fallback_value: Any = None):
    """Decorator to provide fallback when Redis is unavailable."""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            try:
                return func(*args, **kwargs)
            except RedisError as e:
                log.warning(f"Redis operation failed in {func.__name__}, using fallback: {e}")
                return fallback_value

        return wrapper

    return decorator


# Rate limiting specific helpers
class RateLimiter:
    """Token bucket rate limiter with Redis backend and local fallback."""

    def __init__(self, redis_client: ResilientRedis, key_prefix: str = "ratelimit"):
        self.redis = redis_client
        self.key_prefix = key_prefix

    def check_limit(self, identifier: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        """
        Check if identifier is within rate limit.
        Returns (allowed, remaining_requests).
        """
        if self.redis.is_degraded():
            # In degraded mode, allow all requests but log warning
            log.warning(f"Rate limiter degraded - allowing request for {identifier}")
            return True, limit

        key = f"{self.key_prefix}:{identifier}"
        current = self.redis.get(key)

        if current is None:
            # First request in window
            self.redis.setex(key, window_seconds, "1")
            return True, limit - 1

        count = int(current)
        if count >= limit:
            ttl = self.redis.ttl(key)
            return False, 0

        self.redis.incr(key)
        return True, limit - count - 1


# Session store helpers
class SessionStore:
    """Session storage with Redis backend and graceful degradation."""

    def __init__(self, redis_client: ResilientRedis, key_prefix: str = "session"):
        self.redis = redis_client
        self.key_prefix = key_prefix
        self._local_fallback: dict[str, tuple[str, float]] = {}  # key -> (value, expiry)

    def _key(self, session_id: str) -> str:
        return f"{self.key_prefix}:{session_id}"

    def get(self, session_id: str) -> Optional[str]:
        if self.redis.is_degraded():
            # Check local fallback
            key = self._key(session_id)
            if key in self._local_fallback:
                value, expiry = self._local_fallback[key]
                if time.time() < expiry:
                    return value
                else:
                    del self._local_fallback[key]
            return None

        return self.redis.get(self._key(session_id))

    def set(self, session_id: str, value: str, ttl_seconds: int) -> bool:
        if self.redis.is_degraded():
            # Store in local fallback
            key = self._key(session_id)
            self._local_fallback[key] = (value, time.time() + ttl_seconds)
            # Clean up expired entries periodically
            if len(self._local_fallback) > 1000:
                self._cleanup_local()
            return True

        return self.redis.setex(self._key(session_id), ttl_seconds, value)

    def delete(self, session_id: str) -> bool:
        if self.redis.is_degraded():
            key = self._key(session_id)
            if key in self._local_fallback:
                del self._local_fallback[key]
                return True
            return False

        return self.redis.delete(self._key(session_id)) > 0

    def _cleanup_local(self):
        now = time.time()
        expired = [k for k, (_, exp) in self._local_fallback.items() if exp < now]
        for k in expired:
            del self._local_fallback[k]