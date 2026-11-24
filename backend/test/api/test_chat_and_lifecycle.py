"""Phases 5-7 gate against a real database (docs/19): visitor bootstrap,
grounded streaming chat, lead + feedback, tenant/visitor isolation, quota
guard, idempotent replays, domain allowlist, history, account-deletion
cleanup, crawl import, dashboard/usage.

Requires TEST_DATABASE_URL (migrated to head, i.e. including 0008). All
providers (embedding, Pinecone, LLM) are stubbed -- no network.
"""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

PASSWORD = "correct-horse-battery"


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


@pytest.fixture
def llm_calls(monkeypatch):
    """Stubs embedding, vector search and the LLM; records LLM invocations."""
    from app.chat import llm, pipeline

    calls = []

    async def fake_stream(messages):
        calls.append(messages)
        for piece in ("We open ", "at 9 [1]."):
            yield piece

    monkeypatch.setattr(llm, "stream_completion", fake_stream)
    monkeypatch.setattr(pipeline, "_embed_query", lambda text: [0.1] * 4)
    monkeypatch.setattr(pipeline, "_vector_query", lambda company, vec, versions: [{"id": "vec-" + versions[0], "score": 0.99}])
    return calls


def signup(client, db_conn, email):
    from app.auth import service

    client.post("/api/v1/auth/signup", json={"email": email, "password": PASSWORD, "name": "T"})
    user = service.get_user_by_email(db_conn, email)
    raw = service._create_auth_token(db_conn, user["id"], "verify_email", 3600)  # noqa: SLF001
    db_conn.commit()
    client.post("/api/v1/auth/verify-email", json={"token": raw})
    token = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD}).json()["session_token"]
    return {"Authorization": f"Bearer {token}"}


def seed_published_bot(client, db_conn, headers, text="We open at 9 and close at 5."):
    """Text source -> mark its version ready with one chunk -> publish."""
    created = client.post("/api/v1/sources/text", json={"title": "Hours", "text": text}, headers=headers).json()
    doc_id = created["document_id"]
    version = db_conn.execute("SELECT id FROM document_versions WHERE document_id = %s", (doc_id,)).fetchone()["id"]
    db_conn.execute("UPDATE document_versions SET status = 'ready', chunk_count = 1, ready_at = now() WHERE id = %s", (version,))
    db_conn.execute("UPDATE documents SET active_version_id = %s WHERE id = %s", (version, doc_id))
    db_conn.execute(
        "INSERT INTO chunks (version_id, ordinal, page, text, vector_id) VALUES (%s, 0, 1, %s, %s)",
        (version, text, f"vec-{version}"),
    )
    db_conn.commit()
    client.patch("/api/v1/bot", json={"draft_revision": 1, "config_patch": {"name": "Acme", "fallback_message": "Sorry."}}, headers=headers)
    pub = client.post("/api/v1/bot/publish", json={"selected_document_version_ids": [str(version)]}, headers=headers)
    assert pub.status_code == 201, pub.text
    bot = client.get("/api/v1/bot", headers=headers).json()
    return {"public_id": bot["public_id"], "version_id": str(version), "doc_id": doc_id, "publication_id": pub.json()["publication_id"]}


def visitor(client, public_id, origin=None):
    headers = {"Origin": origin} if origin else {}
    r = client.post(f"/api/v1/public/bots/{public_id}/sessions", headers=headers)
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['visitor_token']}"}


def sse_events(response):
    events = []
    for block in response.text.split("\n\n"):
        block = block.strip()
        if block.startswith("event:"):
            name, data = block.split("\n", 1)
            events.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


def ask(client, vh, conv_id, text="When do you open?", key=None):
    headers = dict(vh)
    if key:
        headers["Idempotency-Key"] = key
    return client.post(f"/api/v1/public/conversations/{conv_id}/messages", json={"text": text}, headers=headers)


def test_full_visitor_flow_history_lead_feedback(client, db_conn, llm_calls):
    owner = signup(client, db_conn, f"flow-{uuid.uuid4().hex[:6]}@example.com")
    bot = seed_published_bot(client, db_conn, owner)

    cfg = client.get(f"/api/v1/public/bots/{bot['public_id']}/config")
    assert cfg.status_code == 200 and cfg.json()["name"] == "Acme" and cfg.json()["lead_capture_enabled"] is True

    vh = visitor(client, bot["public_id"])
    conv = client.post("/api/v1/public/conversations", headers=vh).json()["conversation_id"]
    resp = ask(client, vh, conv)
    assert resp.headers["content-type"].startswith("text/event-stream")
    events = sse_events(resp)
    assert [e for e, _ in events] == ["meta", "sources", "delta", "delta", "done"]
    assert [d["seq"] for _, d in events] == [1, 2, 3, 4, 5]
    assert events[1][1]["sources"][0]["title"] == "Hours"
    message_id = events[-1][1]["message_id"]

    assert client.post(f"/api/v1/public/messages/{message_id}/feedback", json={"rating": 1}, headers=vh).status_code == 201
    lead = client.post(f"/api/v1/public/conversations/{conv}/lead", json={"name": "Sam", "email": "sam@example.com", "consent": True}, headers=vh)
    assert lead.status_code == 201
    assert client.post(f"/api/v1/public/conversations/{conv}/lead", json={"name": "Sam", "consent": True}, headers=vh).status_code == 409
    assert client.post(f"/api/v1/public/conversations/{conv}/lead", json={"name": "Sam", "consent": False}, headers=vh).status_code == 422

    listing = client.get("/api/v1/conversations?has_feedback=true", headers=owner).json()
    assert [c["id"] for c in listing["items"]] == [conv] and listing["items"][0]["has_lead"] is True
    detail = client.get(f"/api/v1/conversations/{conv}", headers=owner).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]
    assert detail["messages"][1]["content"] == "We open at 9 [1]." and detail["messages"][1]["status"] == "completed"
    assert detail["lead"]["values"] == {"name": "Sam", "email": "sam@example.com"}

    kinds = {r["event_type"] for r in db_conn.execute("SELECT event_type FROM analytics_events").fetchall()}
    assert {"conversation_started", "message_sent", "feedback_given", "lead_submitted"} <= kinds
    export = client.get(f"/api/v1/conversations/{conv}/export", headers=owner)
    assert export.status_code == 200 and "attachment" in export.headers["content-disposition"]


def test_lead_is_skippable_chat_works_without_it(client, db_conn, llm_calls):
    owner = signup(client, db_conn, f"skip-{uuid.uuid4().hex[:6]}@example.com")
    bot = seed_published_bot(client, db_conn, owner)
    vh = visitor(client, bot["public_id"])
    conv = client.post("/api/v1/public/conversations", headers=vh).json()["conversation_id"]
    assert sse_events(ask(client, vh, conv))[-1][0] == "done"


def test_isolation_between_visitors_owners_and_token_types(client, db_conn, llm_calls):
    a = signup(client, db_conn, f"iso-a-{uuid.uuid4().hex[:6]}@example.com")
    b = signup(client, db_conn, f"iso-b-{uuid.uuid4().hex[:6]}@example.com")
    bot = seed_published_bot(client, db_conn, a)
    v1, v2 = visitor(client, bot["public_id"]), visitor(client, bot["public_id"])
    conv = client.post("/api/v1/public/conversations", headers=v1).json()["conversation_id"]
    message_id = sse_events(ask(client, v1, conv))[-1][1]["message_id"]

    assert ask(client, v2, conv).status_code == 404  # another visitor's conversation
    assert client.post(f"/api/v1/public/messages/{message_id}/feedback", json={"rating": 1}, headers=v2).status_code == 404
    assert client.post(f"/api/v1/public/conversations/{conv}/lead", json={"name": "x", "consent": True}, headers=v2).status_code == 404

    assert client.get(f"/api/v1/conversations/{conv}", headers=b).status_code == 404  # other owner
    assert client.delete(f"/api/v1/conversations/{conv}", headers=b).status_code == 404
    assert client.get(f"/api/v1/conversations/{conv}/export", headers=b).status_code == 404
    assert client.get("/api/v1/conversations", headers=b).json()["items"] == []
    assert client.post(f"/api/v1/public/messages/{message_id}/feedback", json={"rating": -1}, headers=b).status_code == 404

    assert client.post("/api/v1/public/conversations", headers=a).status_code == 401  # owner token is not a visitor token
    assert client.get("/api/v1/bot", headers=v1).status_code == 401  # visitor token is not an owner session


def test_unpublish_immediately_denies_visitors(client, db_conn, llm_calls):
    owner = signup(client, db_conn, f"unpub-{uuid.uuid4().hex[:6]}@example.com")
    bot = seed_published_bot(client, db_conn, owner)
    vh = visitor(client, bot["public_id"])
    conv = client.post("/api/v1/public/conversations", headers=vh).json()["conversation_id"]
    client.post("/api/v1/bot/unpublish", headers=owner)
    assert ask(client, vh, conv).status_code == 404
    assert client.get(f"/api/v1/public/bots/{bot['public_id']}/config").status_code == 404
    assert client.post(f"/api/v1/public/bots/{bot['public_id']}/sessions").status_code == 404


def test_deleted_source_is_no_longer_retrievable(client, db_conn, llm_calls):
    owner = signup(client, db_conn, f"delsrc-{uuid.uuid4().hex[:6]}@example.com")
    bot = seed_published_bot(client, db_conn, owner)
    vh = visitor(client, bot["public_id"])
    conv = client.post("/api/v1/public/conversations", headers=vh).json()["conversation_id"]
    client.delete(f"/api/v1/documents/{bot['doc_id']}", headers=owner)
    events = sse_events(ask(client, vh, conv))
    assert events[-1][0] == "done" and events[2][1]["text"] == "Sorry."  # fallback, no evidence
    assert llm_calls == []


def test_domain_allowlist_gates_bootstrap(client, db_conn, llm_calls):
    owner = signup(client, db_conn, f"dom-{uuid.uuid4().hex[:6]}@example.com")
    bot = seed_published_bot(client, db_conn, owner)
    assert client.put("/api/v1/bot/domains", json={"allowed_domains": ["https://bad.com"]}, headers=owner).status_code == 422
    ok = client.put("/api/v1/bot/domains", json={"allowed_domains": ["example.com", "*.shop.example.com"]}, headers=owner)
    assert ok.status_code == 200 and ok.json()["allowed_domains"] == ["example.com", "*.shop.example.com"]

    pid = bot["public_id"]
    assert client.get(f"/api/v1/public/bots/{pid}/config", headers={"Origin": "https://evil.com"}).status_code == 403
    assert client.post(f"/api/v1/public/bots/{pid}/sessions").status_code == 403
    assert client.get(f"/api/v1/public/bots/{pid}/config", headers={"Origin": "https://example.com"}).status_code == 200
    assert client.post(f"/api/v1/public/bots/{pid}/sessions", headers={"Origin": "https://a.shop.example.com"}).status_code == 201


def test_quota_guard_blocks_before_any_provider_call(client, db_conn, llm_calls, monkeypatch):
    from app.config import settings

    owner = signup(client, db_conn, f"quota-{uuid.uuid4().hex[:6]}@example.com")
    bot = seed_published_bot(client, db_conn, owner)
    vh = visitor(client, bot["public_id"])
    conv = client.post("/api/v1/public/conversations", headers=vh).json()["conversation_id"]

    monkeypatch.setattr(settings(), "company_chat_daily_limit", 1)
    assert sse_events(ask(client, vh, conv))[-1][0] == "done"
    assert len(llm_calls) == 1

    blocked = ask(client, vh, conv, "second question")
    assert blocked.status_code == 429 and blocked.json()["code"] == "quota_exhausted"
    assert int(blocked.headers["retry-after"]) > 0
    assert len(llm_calls) == 1  # call-count assertion: exhaustion never reaches the provider

    usage = client.get("/api/v1/usage", headers=owner).json()
    assert usage["quota_state"] == "exhausted" and "next_reset_at" in usage
    assert not any("upgrade" in k or "price" in k for k in usage)
    assert client.get("/api/v1/dashboard", headers=owner).json()["usage_summary"]["quota_state"] == "exhausted"


def test_chat_idempotency_key_replays_without_a_second_generation(client, db_conn, llm_calls):
    owner = signup(client, db_conn, f"idem-{uuid.uuid4().hex[:6]}@example.com")
    bot = seed_published_bot(client, db_conn, owner)
    vh = visitor(client, bot["public_id"])
    conv = client.post("/api/v1/public/conversations", headers=vh).json()["conversation_id"]

    first = sse_events(ask(client, vh, conv, key="k-1"))
    second = sse_events(ask(client, vh, conv, key="k-1"))
    assert second[0][1].get("replayed") is True and second[-1][0] == "done"
    assert "".join(d["text"] for e, d in first if e == "delta") == second[2][1]["text"]
    assert len(llm_calls) == 1
    count = db_conn.execute("SELECT COUNT(*) AS n FROM messages WHERE conversation_id = %s", (conv,)).fetchone()["n"]
    assert count == 2


def test_publish_idempotency_key(client, db_conn, llm_calls):
    owner = signup(client, db_conn, f"pubidem-{uuid.uuid4().hex[:6]}@example.com")
    bot = seed_published_bot(client, db_conn, owner)
    body = {"selected_document_version_ids": [bot["version_id"]]}
    h = {**owner, "Idempotency-Key": "pub-1"}
    first = client.post("/api/v1/bot/publish", json=body, headers=h)
    second = client.post("/api/v1/bot/publish", json=body, headers=h)
    assert first.status_code == second.status_code == 201 and first.json() == second.json()
    assert second.headers.get("idempotent-replayed") == "true"
    other = client.post("/api/v1/bot/publish", json={"selected_document_version_ids": [str(uuid.uuid4())]}, headers=h)
    assert other.status_code == 409 and other.json()["code"] == "idempotency_key_reuse"
    assert client.post("/api/v1/bot/publish", json={"selected_document_version_ids": ["nope"]}, headers=owner).status_code == 422


def test_owner_preview_uses_draft_scope_and_same_pipeline(client, db_conn, llm_calls):
    owner = signup(client, db_conn, f"prev-{uuid.uuid4().hex[:6]}@example.com")
    seed_published_bot(client, db_conn, owner)
    conv = client.post("/api/v1/bot/preview/conversations", headers=owner)
    assert conv.status_code == 201
    r = client.post("/api/v1/bot/preview/chat", json={"conversation_id": conv.json()["conversation_id"], "message": "hours?"}, headers=owner)
    assert [e for e, _ in sse_events(r)][-1] == "done"
    assert client.get("/api/v1/conversations", headers=owner).json()["items"] == []  # previews are not visitor history
    other = signup(client, db_conn, f"prev2-{uuid.uuid4().hex[:6]}@example.com")
    assert client.post("/api/v1/bot/preview/chat", json={"conversation_id": conv.json()["conversation_id"], "message": "x"}, headers=other).status_code == 404


def test_account_deletion_revokes_immediately_and_cleanup_job_purges(client, db_conn, llm_calls, monkeypatch):
    from app.jobs import executors
    from app.providers import vector_store

    owner = signup(client, db_conn, f"del-{uuid.uuid4().hex[:6]}@example.com")
    bot = seed_published_bot(client, db_conn, owner)
    vh = visitor(client, bot["public_id"])
    conv = client.post("/api/v1/public/conversations", headers=vh).json()["conversation_id"]
    sse_events(ask(client, vh, conv))

    deleted = client.request("DELETE", "/api/v1/me", json={"confirm": True, "current_password": PASSWORD}, headers=owner)
    assert deleted.status_code == 202 and deleted.json()["cleanup_job_id"]

    assert client.get("/api/v1/me", headers=owner).status_code == 401  # sessions revoked
    assert client.get(f"/api/v1/public/bots/{bot['public_id']}/config").status_code == 404  # public access revoked
    assert ask(client, vh, conv).status_code == 404

    vectors = []
    monkeypatch.setattr(vector_store, "delete_company_vectors", lambda company_id: vectors.append(company_id))
    job = db_conn.execute("SELECT * FROM jobs WHERE id = %s", (deleted.json()["cleanup_job_id"],)).fetchone()
    executors.company_cleanup_executor(db_conn, job, lambda: True)
    db_conn.commit()

    assert vectors == [str(job["company_id"])]
    for table in ("documents", "bots", "usage_daily"):
        n = db_conn.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE company_id = %s", (job["company_id"],)).fetchone()["n"]
        assert n == 0, table
    assert db_conn.execute("SELECT COUNT(*) AS n FROM conversations WHERE id = %s", (conv,)).fetchone()["n"] == 0


def test_crawl_discover_then_import_selection(client, db_conn):
    email = f"crawl-{uuid.uuid4().hex[:6]}@example.com"
    owner = signup(client, db_conn, email)
    assert client.post("/api/v1/sources/crawl/discover", json={"root_url": "http://169.254.169.254/"}, headers=owner).status_code == 422  # SSRF

    company_id = db_conn.execute(
        "SELECT c.id FROM companies c JOIN users u ON u.id = c.owner_user_id WHERE u.normalized_email = %s", (email,)
    ).fetchone()["id"]
    pages = [{"url": "https://example.com/a", "title": "a"}, {"url": "https://example.com/b", "title": "b"}]
    crawl_id = db_conn.execute(
        "INSERT INTO crawl_jobs (company_id, root_url, max_pages, status, discovered_pages) VALUES (%s, 'https://example.com', 5, 'completed', %s::jsonb) RETURNING id",
        (company_id, json.dumps(pages)),
    ).fetchone()["id"]
    db_conn.commit()

    assert client.get(f"/api/v1/crawl-jobs/{crawl_id}", headers=owner).json()["status"] == "completed"
    bad = client.post(f"/api/v1/crawl-jobs/{crawl_id}/import", json={"selected_urls": ["https://evil.com/x"]}, headers=owner)
    assert bad.status_code == 422 and bad.json()["code"] == "page_not_discovered"
    ok = client.post(f"/api/v1/crawl-jobs/{crawl_id}/import", json={"selected_urls": ["https://example.com/a"]}, headers=owner)
    assert ok.status_code == 202 and len(ok.json()["document_ids"]) == 1 and len(ok.json()["job_ids"]) == 1
    again = client.post(f"/api/v1/crawl-jobs/{crawl_id}/import", json={"selected_urls": ["https://example.com/a"]}, headers=owner)
    assert again.json()["document_ids"] == []  # re-import never duplicates a source


def test_profile_company_and_source_management_routes(client, db_conn):
    owner = signup(client, db_conn, f"mgmt-{uuid.uuid4().hex[:6]}@example.com")
    assert client.patch("/api/v1/me", json={"name": "New Name"}, headers=owner).status_code == 200
    assert client.get("/api/v1/me", headers=owner).json()["name"] == "New Name"
    assert client.patch("/api/v1/me", json={"avatar_key": "../../etc/passwd"}, headers=owner).status_code == 422
    assert client.post("/api/v1/company", json={"name": "Dup"}, headers=owner).status_code == 409
    export = client.get("/api/v1/company/export", headers=owner)
    assert export.status_code == 200
    blob = export.text.lower()
    for forbidden in ("password_hash", "secret", "session_token", "api_key"):
        assert forbidden not in blob

    created = client.post("/api/v1/sources/text", json={"title": "Old", "text": "hello"}, headers=owner).json()
    doc_id, job_id = created["document_id"], created["job_id"]
    assert client.patch(f"/api/v1/documents/{doc_id}", json={"title": "Renamed"}, headers=owner).json()["title"] == "Renamed"
    assert client.get(f"/api/v1/documents/{doc_id}/content", headers=owner).status_code == 409  # not ready yet
    job = client.get(f"/api/v1/jobs/{job_id}", headers=owner).json()
    assert job["state"] in ("queued", "processing") and "attempts" in job
    listing = client.get("/api/v1/documents?q=Renam&type=text", headers=owner).json()
    assert [d["id"] for d in listing["items"]] == [doc_id] and listing["items"][0]["status"] == "pending"
    assert client.get("/api/v1/documents?state=ready", headers=owner).json()["items"] == []

    dash = client.get("/api/v1/dashboard", headers=owner).json()
    assert dash["source_counts_by_state"] == {"pending": 1}
    assert {"setup_checklist", "conversation_count", "usage_summary"} <= set(dash)
    embed = client.get("/api/v1/bot/embed", headers=owner).json()
    assert embed["public_id"] in embed["script_snippet"]
