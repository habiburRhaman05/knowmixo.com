"""Regression for launch/00-BUILD-HEALTH.md §2.1 — Redis resilience must
read from `settings()` so it can see the value that pydantic_settings
loaded from `.env`. Previously it read `os.environ` directly which meant
production boots without a shell-exported REDIS_URL silently failed."""
import os

import pytest


def test_resilient_redis_reads_from_settings(monkeypatch):
    # Force os.environ to be empty — this is the historical failure mode
    # where os.environ.get("REDIS_URL") returned "" and the layer crashed.
    monkeypatch.delenv("REDIS_URL", raising=False)

    from app import config as config_module
    from app import redis_resilience

    config_module.settings.cache_clear()

    class FakeSettings:
        redis_url = "redis://fake-host:6379/0"

    monkeypatch.setattr(config_module, "settings", lambda: FakeSettings)

    # Reset any cached instance so we re-read settings.
    redis_resilience.reset_redis()

    r = redis_resilience.ResilientRedis()
    assert r.url == "redis://fake-host:6379/0"


def test_resilient_redis_falls_back_to_env_if_settings_unavailable(monkeypatch):
    # If `app.config.settings` cannot be imported, the layer should still
    # degrade to os.environ rather than crash on import.
    monkeypatch.setenv("REDIS_URL", "redis://env-fallback:6379/0")

    from app import redis_resilience

    # Simulate settings() raising by temporarily replacing it.
    import sys

    sys.modules.pop("app.config", None)

    class _Boom:
        def __getattr__(self, _):
            raise RuntimeError("unavailable")

    sys.modules["app.config"] = _Boom()
    try:
        redis_resilience.reset_redis()
        r = redis_resilience.ResilientRedis()
        assert r.url == "redis://env-fallback:6379/0"
    finally:
        sys.modules.pop("app.config", None)


def test_resilient_redis_prefers_explicit_url(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://env:6379")
    from app import redis_resilience

    r = redis_resilience.ResilientRedis(url="redis://explicit:6379")
    assert r.url == "redis://explicit:6379"
