"""D1.2 — AUTH_SECRET startup validator (launch/03-RISKS-AND-BLOCKERS R02)."""
import pytest

BASE = dict(
    DATABASE_URL="postgresql://u:p@l/x",
    REDIS_URL="redis://l",
    PINECONE_API_KEY="k",
    PINECONE_HOST="h",
    GROQ_API_KEY="g",
    CLOUDFLARE_ACCOUNT_ID="a",
    CLOUDFLARE_API_TOKEN="t",
    ENCRYPTION_KEY="x" * 64,
)


def _env(monkeypatch, **overrides):
    for k, v in {**BASE, **overrides}.items():
        monkeypatch.setenv(k, v)


def test_production_without_auth_secret_refuses_boot(monkeypatch):
    _env(monkeypatch, APP_ENV="production", AUTH_SECRET="")
    from app import config

    config.settings.cache_clear()
    with pytest.raises(ValueError, match="AUTH_SECRET"):
        config.Settings()


def test_production_with_short_secret_refuses_boot(monkeypatch):
    _env(monkeypatch, APP_ENV="production", AUTH_SECRET="too-short")
    from app import config

    config.settings.cache_clear()
    with pytest.raises(ValueError, match="AUTH_SECRET"):
        config.Settings()


def test_production_with_strong_secret_boots(monkeypatch):
    _env(monkeypatch, APP_ENV="production", AUTH_SECRET="k" * 48)
    from app import config

    config.settings.cache_clear()
    s = config.Settings()
    assert s.auth_secret == "k" * 48


def test_dev_without_auth_secret_boots_with_warning(monkeypatch, caplog):
    _env(monkeypatch, APP_ENV="development", AUTH_SECRET="")
    from app import config

    config.settings.cache_clear()
    with caplog.at_level("WARNING"):
        config.Settings()
    assert any("AUTH_SECRET" in r.message for r in caplog.records)
