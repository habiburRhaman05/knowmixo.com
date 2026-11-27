import logging
import uuid
from pathlib import Path

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException

from app import health
from app.actions.router import router as actions_router
from app.analytics.router import router as analytics_router
from app.auth.router import router as auth_router
from app.billing.router import billing_router, webhook_router as billing_webhook_router
from app.bots.router import router as bots_router
from app.channels.router import router as channels_router
from app.chat.rag_v2.traces_router import router as rag_traces_router
from app.dashboard.router import router as dashboard_router
from app.escalation.router import router as escalation_router, public_router as escalation_public_router
from app.handoff.router import router as handoff_router
from app.integrations.router import router as slack_router, public_router as slack_public_router
from app.observability import initialize
from app.profile_router import router as profile_router
from app.public.router import router as public_router
from app.public_api.keys_router import router as api_keys_router
from app.public_api.problem_details import PublicAPIError, problem_response
from app.public_api.router import router as public_api_router
from app.quality.router import router as quality_router
from app.realtime.router import router as realtime_router
from app.security.mfa_router import router as mfa_router
from app.sources.router import router as sources_router
from app.team.router import router as team_router, public_router as team_public_router
from app.webhooks.router import router as webhooks_router

initialize()
log = logging.getLogger(__name__)

BASE = Path(__file__).resolve().parent
app = FastAPI(title="Knowmivo", docs_url="/api/docs")
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")


class RequestIdMiddleware:
    """Pure-ASGI (not BaseHTTPMiddleware) so SSE streams are never buffered.
    Honours a caller-supplied X-Request-ID, otherwise mints one, exposes it
    as request.state.request_id and echoes it on every response."""

    def __init__(self, asgi_app):
        self.app = asgi_app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        incoming = dict(scope.get("headers") or []).get(b"x-request-id", b"").decode()[:64]
        request_id = incoming if incoming.replace("-", "").isalnum() and incoming else str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"]
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_id)


app.add_middleware(RequestIdMiddleware)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or str(uuid.uuid4())


@app.exception_handler(PublicAPIError)
async def public_api_error_handler(request: Request, exc: PublicAPIError):
    return problem_response(request, exc)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Error shape from docs/16: {code, message, retry_after_seconds?, fields?}
    plus request_id. The original `detail` is preserved for existing
    clients/tests."""
    detail = exc.detail if isinstance(exc.detail, dict) else {"code": "error", "message": str(exc.detail)}
    body = {"detail": exc.detail, "request_id": _request_id(request)}
    body.update({k: v for k, v in detail.items() if k in ("code", "message", "retry_after_seconds", "fields")})
    return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    fields = [".".join(str(p) for p in e.get("loc", ()) if p != "body") for e in errors]
    return JSONResponse(
        {
            "detail": jsonable(errors),
            "code": "validation_error",
            "message": "Request validation failed.",
            "fields": fields,
            "request_id": _request_id(request),
        },
        status_code=422,
    )


@app.exception_handler(psycopg.OperationalError)
@app.exception_handler(psycopg.InterfaceError)
async def database_unavailable_handler(request: Request, exc: Exception):
    """A connection that dies mid-request (Postgres restart, network
    partition, Neon compute suspend) is infrastructure, not a bug in the
    request -- 503 tells the client to retry, unlike the generic 500 the
    Exception handler below would otherwise return. Whatever the request
    was doing is rolled back by Postgres itself (the dead connection's
    transaction is never committed), so there is no partial-commit risk
    here regardless of which statement was in flight."""
    log.warning("database unavailable request_id=%s: %s", _request_id(request), exc)
    return JSONResponse(
        {"code": "database_unavailable", "message": "The database is temporarily unavailable. Please retry.", "request_id": _request_id(request)},
        status_code=503,
        headers={"Retry-After": "5"},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.exception("unhandled error request_id=%s", _request_id(request))
    return JSONResponse(
        {"code": "internal_error", "message": "Something went wrong.", "request_id": _request_id(request)},
        status_code=500,
    )


def jsonable(errors):
    from fastapi.encoders import jsonable_encoder

    return jsonable_encoder(errors, custom_encoder={Exception: str})


app.include_router(auth_router)
app.include_router(actions_router)
app.include_router(analytics_router)
app.include_router(billing_router)
app.include_router(billing_webhook_router)
app.include_router(profile_router)
app.include_router(dashboard_router)
app.include_router(escalation_router)
app.include_router(escalation_public_router)
app.include_router(handoff_router)
app.include_router(slack_router)
app.include_router(slack_public_router)
app.include_router(mfa_router)
app.include_router(realtime_router)
app.include_router(sources_router)
app.include_router(team_router)
app.include_router(team_public_router)
app.include_router(bots_router)
app.include_router(channels_router)
app.include_router(public_router)
app.include_router(api_keys_router)
app.include_router(public_api_router)
app.include_router(quality_router)
app.include_router(rag_traces_router)
app.include_router(webhooks_router)


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "mode": "development"})


@app.get("/health/live")
@app.get("/api/v1/health/live")
def live():
    return {"status": "alive"}


@app.get("/health/ready")
@app.get("/api/v1/health/ready")
def ready():
    """Postgres + Redis + Pinecone reachability only -- never a paid
    generation call (docs/16 "Health")."""
    failing = health.failing_dependencies()
    if failing:
        return JSONResponse({"status": "unavailable", "failing_dependencies": failing}, status_code=503)
    return {"status": "ready"}
