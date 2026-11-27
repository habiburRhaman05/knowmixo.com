"""Day 1 observability regressions — launch/13 D1.8."""


def test_initialize_is_safe_without_env(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN_BACKEND", raising=False)
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.delenv("RIUS_API_KEY", raising=False)

    from app import observability

    # Must not raise even if neither provider is configured.
    observability.initialize()


def test_scrub_strips_sensitive_headers():
    from app import observability

    event = {
        "request": {
            "data": {"password": "pw"},
            "cookies": {"session": "x"},
            "headers": {"Authorization": "Bearer abc", "X-Request-Id": "r-1"},
        }
    }
    cleaned = observability._scrub_event(event, {})  # type: ignore[attr-defined]
    assert cleaned is not None
    assert "data" not in cleaned["request"]
    assert "cookies" not in cleaned["request"]
    assert cleaned["request"]["headers"]["Authorization"] == "[filtered]"
    assert cleaned["request"]["headers"]["X-Request-Id"] == "r-1"
