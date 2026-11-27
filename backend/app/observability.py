"""Privacy-first observability. Nothing is sent without an explicit
`SENTRY_DSN_BACKEND` env var. PII is scrubbed before send.

Day-1 (launch/13 D1.8): Sentry primary; the earlier Rius hook is retained
only as an opt-in fallback for environments that still have it configured.
"""
import logging
import os
from functools import wraps

log = logging.getLogger(__name__)


def _scrub_event(event: dict, _hint: dict) -> dict | None:
    """Last-chance PII scrub. Drops request bodies and auth headers."""
    try:
        req = event.get("request") or {}
        if isinstance(req, dict):
            req.pop("data", None)
            req.pop("cookies", None)
            headers = req.get("headers") or {}
            if isinstance(headers, dict):
                for k in list(headers):
                    if k.lower() in ("authorization", "cookie", "set-cookie", "x-api-key"):
                        headers[k] = "[filtered]"
    except Exception:  # noqa: BLE001 -- never raise from the SDK callback
        pass
    return event


def _init_sentry() -> bool:
    dsn = os.environ.get("SENTRY_DSN_BACKEND") or os.environ.get("SENTRY_DSN")
    if not dsn:
        log.info("Sentry DSN not set — skipping init")
        return False
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except ImportError:
        log.info("sentry-sdk not installed — skipping init")
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=os.environ.get("APP_ENV", "development"),
        release=os.environ.get("APP_RELEASE", "dev"),
        send_default_pii=False,
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_RATE", "0.1")),
        profiles_sample_rate=float(os.environ.get("SENTRY_PROFILES_RATE", "0.0")),
        before_send=_scrub_event,
        integrations=[FastApiIntegration(), StarletteIntegration()],
    )
    log.info("Sentry initialized")
    return True


def _init_rius_legacy() -> None:
    from dotenv import load_dotenv

    load_dotenv()
    if not os.getenv("RIUS_API_KEY") or os.getenv("RIUS_DISABLED", "false").lower() in ("1", "true", "yes"):
        return
    try:
        import rius  # type: ignore[import-not-found]

        rius.init(service_name=os.getenv("RIUS_SERVICE_NAME", "knowmivo-api"), capture_content=False)
        log.info("Rius observability enabled (legacy fallback)")
    except Exception:
        log.exception("Rius initialization failed; continuing without legacy tracing")


def initialize() -> None:
    """Call once, before instrumented app modules are loaded."""
    if _init_sentry():
        return
    # Fall through to the legacy hook only when Sentry isn't configured.
    _init_rius_legacy()

def trace(name):
    """Decorate sync/async functions; never export arguments or return values."""
    def decorate(fn):
        try:
            import rius
            return rius.observe(name=name, capture_input=False, capture_output=False)(fn)
        except ImportError:
            return fn
    return decorate
