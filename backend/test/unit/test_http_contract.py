"""HTTP-level contract checks that need no database: auth fails closed,
error/request_id shape (docs/16 header), health readiness, visitor/owner
token separation. Uses FastAPI's TestClient with the DB layer never reached
(or stubbed) so nothing external is contacted."""
import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app, raise_server_exceptions=False)

OWNER_ROUTES = [
    ("GET", "/api/v1/me"), ("PATCH", "/api/v1/me"), ("GET", "/api/v1/company"), ("POST", "/api/v1/company"),
    ("GET", "/api/v1/company/export"), ("GET", "/api/v1/dashboard"), ("GET", "/api/v1/usage"),
    ("GET", "/api/v1/documents"), ("GET", "/api/v1/documents/x"), ("PATCH", "/api/v1/documents/x"),
    ("GET", "/api/v1/documents/x/content"), ("GET", "/api/v1/jobs/x"), ("POST", "/api/v1/jobs/x/retry"),
    ("GET", "/api/v1/crawl-jobs/x"), ("POST", "/api/v1/sources/crawl/discover"),
    ("GET", "/api/v1/bot"), ("PATCH", "/api/v1/bot"), ("POST", "/api/v1/bot/publish"), ("POST", "/api/v1/bot/unpublish"),
    ("PUT", "/api/v1/bot/domains"), ("GET", "/api/v1/bot/embed"), ("GET", "/api/v1/bot/export"),
    ("POST", "/api/v1/bot/preview/conversations"), ("POST", "/api/v1/bot/preview/chat"),
    ("GET", "/api/v1/conversations"), ("GET", "/api/v1/conversations/x"), ("DELETE", "/api/v1/conversations/x"),
    ("GET", "/api/v1/conversations/x/export"), ("POST", "/api/v1/auth/logout"), ("POST", "/api/v1/auth/logout-all"),
    ("GET", "/api/v1/webhooks/endpoints"),
]


@pytest.mark.parametrize("method,path", OWNER_ROUTES)
def test_owner_routes_fail_closed_without_a_session(method, path):
    r = client.request(method, path, json={})
    assert r.status_code in (401, 422), (method, path, r.status_code)
    if r.status_code == 401:
        assert r.json()["code"] == "unauthenticated"
        assert r.json()["request_id"]


@pytest.mark.parametrize(
    "method,path",
    [("POST", "/api/v1/public/conversations"), ("POST", "/api/v1/public/conversations/x/messages"),
     ("POST", "/api/v1/public/conversations/x/lead"), ("POST", "/api/v1/public/messages/x/feedback")],
)
def test_visitor_routes_require_a_token(method, path):
    r = client.request(method, path, json={"text": "hi", "consent": True, "rating": 1})
    assert r.status_code == 401
    assert r.json()["code"] == "unauthenticated"


def test_request_id_is_minted_and_echoed():
    r = client.get("/health/live")
    assert r.status_code == 200 and r.headers["x-request-id"]
    r2 = client.get("/health/live", headers={"X-Request-ID": "abc-123"})
    assert r2.headers["x-request-id"] == "abc-123"
    r3 = client.get("/health/live", headers={"X-Request-ID": "bad id with spaces!!"})
    assert r3.headers["x-request-id"] != "bad id with spaces!!"


def test_validation_errors_use_the_documented_shape():
    r = client.post("/api/v1/auth/signup", json={"email": "not-an-email"})
    body = r.json()
    assert r.status_code == 422
    assert body["code"] == "validation_error" and body["request_id"]
    assert "email" in body["fields"] and isinstance(body["detail"], list)


def test_unknown_route_has_error_shape_with_request_id():
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404 and r.json()["request_id"]


def test_ready_is_503_and_names_only_failing_dependencies(monkeypatch):
    from app import health

    def down():
        raise RuntimeError("postgresql://user:secret@host/db refused")

    monkeypatch.setitem(health.CHECKS, "redis", down)
    monkeypatch.setitem(health.CHECKS, "postgres", lambda: None)
    monkeypatch.setitem(health.CHECKS, "pinecone", lambda: None)
    for path in ("/health/ready", "/api/v1/health/ready"):
        r = client.get(path)
        assert r.status_code == 503
        assert r.json()["failing_dependencies"] == ["redis"]
        assert "secret" not in r.text  # error text never leaks into the response


def test_ready_is_200_when_all_dependencies_are_up(monkeypatch):
    from app import health

    for name in list(health.CHECKS):
        monkeypatch.setitem(health.CHECKS, name, lambda: None)
    assert client.get("/health/ready").json() == {"status": "ready"}


def test_ready_makes_no_generation_call(monkeypatch):
    from app import health
    from app.chat import llm

    for name in list(health.CHECKS):
        monkeypatch.setitem(health.CHECKS, name, lambda: None)

    async def boom(*a, **k):
        raise AssertionError("readiness must never call the LLM")
        yield

    monkeypatch.setattr(llm, "stream_completion", boom)
    assert client.get("/health/ready").status_code == 200


def test_visitor_token_lookup_never_resolves_an_owner_session(monkeypatch):
    """A visitor-token lookup only reads visitor_sessions; an owner session
    token is simply 'invalid' there (separate tables), so owner credentials
    can never be replayed as visitor credentials."""
    from contextlib import contextmanager

    from app.public import router as public

    class Conn:
        def execute(self, sql, params=()):
            assert "visitor_sessions" in sql

            class R:
                def fetchone(self):
                    return None

            return R()

    @contextmanager
    def fake_connection():
        yield Conn()

    monkeypatch.setattr(public, "connection", fake_connection)
    r = client.post("/api/v1/public/conversations", headers={"Authorization": "Bearer an-owner-session-token"})
    assert r.status_code == 401 and r.json()["code"] == "invalid_session"
