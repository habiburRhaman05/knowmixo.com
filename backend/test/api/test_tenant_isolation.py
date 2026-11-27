"""Phase 4 gate (docs/19-BACKEND-SPRINT-PLAN-V2.md): Owner A must never be
able to read, modify, publish, retry, or delete Owner B's bot, documents,
jobs, or publications by substituting IDs. This suite is gate-blocking
and should be re-run after every subsequent phase that touches these
tables, not treated as a one-time check.

Requires TEST_DATABASE_URL pointed at a disposable, migrated database
(migrations 0001-0004 applied). Skipped entirely otherwise.
"""
from fastapi.testclient import TestClient


def _client():
    from app.main import app

    return TestClient(app)


def _consume_latest_verify_token(db_conn, email: str) -> str:
    from app.auth import service

    user = service.get_user_by_email(db_conn, email)
    token = service._create_auth_token(db_conn, user["id"], "verify_email", 3600)  # noqa: SLF001 -- test-only use of internals
    db_conn.commit()
    return token


def _signup_verify_login(client, email: str, db_conn) -> str:
    client.post("/api/v1/auth/signup", json={"email": email, "password": "correct-horse-battery", "name": "T"})
    raw_token = _consume_latest_verify_token(db_conn, email)
    client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    return login.json()["session_token"]


def test_owner_b_cannot_read_or_mutate_owner_a_document_by_id_substitution(db_conn):
    client = _client()
    token_a = _signup_verify_login(client, "tenant-a@example.com", db_conn)
    token_b = _signup_verify_login(client, "tenant-b@example.com", db_conn)

    created = client.post(
        "/api/v1/sources/text",
        json={"title": "A's secret doc", "text": "Confidential content belonging to owner A."},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert created.status_code == 202
    document_id = created.json()["document_id"]
    job_id = created.json()["job_id"]

    headers_b = {"Authorization": f"Bearer {token_b}"}
    assert client.get(f"/api/v1/documents/{document_id}", headers=headers_b).status_code == 404
    assert client.delete(f"/api/v1/documents/{document_id}", headers=headers_b).status_code == 404
    assert client.post(f"/api/v1/documents/{document_id}/refresh", headers=headers_b).status_code == 404
    assert client.post(f"/api/v1/jobs/{job_id}/retry", headers=headers_b).status_code == 404

    # A can still access their own document -- this isn't a blanket 404 bug.
    headers_a = {"Authorization": f"Bearer {token_a}"}
    assert client.get(f"/api/v1/documents/{document_id}", headers=headers_a).status_code == 200


def test_owner_b_cannot_see_owner_a_documents_in_their_own_list(db_conn):
    client = _client()
    token_a = _signup_verify_login(client, "tenant-list-a@example.com", db_conn)
    token_b = _signup_verify_login(client, "tenant-list-b@example.com", db_conn)

    client.post(
        "/api/v1/sources/text",
        json={"title": "A only doc", "text": "Only A should ever see this title."},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    listing = client.get("/api/v1/documents", headers={"Authorization": f"Bearer {token_b}"})
    assert listing.status_code == 200
    titles = [item["title"] for item in listing.json()["items"]]
    assert "A only doc" not in titles


def test_owner_b_cannot_publish_using_owner_a_source_version_id(db_conn):
    """The tenant-isolation-critical check inside publish_bot: a
    document_version_id belonging to another company must never be
    publishable, even if B somehow learns the raw UUID."""
    client = _client()
    token_a = _signup_verify_login(client, "tenant-pub-a@example.com", db_conn)
    token_b = _signup_verify_login(client, "tenant-pub-b@example.com", db_conn)

    created = client.post(
        "/api/v1/sources/text",
        json={"title": "A's pub doc", "text": "Some content for the publish-authorization test."},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    document_id = created.json()["document_id"]
    version_row = db_conn.execute(
        "SELECT id FROM document_versions WHERE document_id = %s", (document_id,)
    ).fetchone()
    version_id = str(version_row["id"])

    # Force it ready directly -- this test is about publish-time
    # authorization, not real ingestion correctness (covered elsewhere).
    db_conn.execute("UPDATE document_versions SET status = 'ready' WHERE id = %s", (version_id,))
    db_conn.commit()

    # B needs its own bot to exist before publish can even reach the
    # cross-tenant ownership check -- get_bot() 404s with "no_bot" first
    # otherwise, which isn't what this test is probing. A bot is lazily
    # created on a company's first source (app/sources/service.py), so
    # give B one of its own.
    client.post(
        "/api/v1/sources/text",
        json={"title": "B's own doc", "text": "Unrelated content so B has a bot."},
        headers={"Authorization": f"Bearer {token_b}"},
    )

    r = client.post(
        "/api/v1/bot/publish",
        json={"selected_document_version_ids": [version_id]},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "source_version_not_found"

    # A can still publish their own ready version.
    r2 = client.post(
        "/api/v1/bot/publish",
        json={"selected_document_version_ids": [version_id]},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert r2.status_code == 201


def test_bots_are_never_addressable_by_id_only_by_session_scope(db_conn):
    """No /bot endpoint accepts a bot ID in the request at all -- company
    scope comes entirely from the session. This means there is no IDOR
    surface to even attempt here, which is a stronger property than
    "checked and denied". This test confirms two owners get two distinct,
    independently-scoped bots."""
    client = _client()
    token_a = _signup_verify_login(client, "tenant-bot-a@example.com", db_conn)
    token_b = _signup_verify_login(client, "tenant-bot-b@example.com", db_conn)

    client.post(
        "/api/v1/sources/text",
        json={"title": "trigger bot creation A", "text": "content"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    client.post(
        "/api/v1/sources/text",
        json={"title": "trigger bot creation B", "text": "content"},
        headers={"Authorization": f"Bearer {token_b}"},
    )

    bot_a = client.get("/api/v1/bot", headers={"Authorization": f"Bearer {token_a}"}).json()
    bot_b = client.get("/api/v1/bot", headers={"Authorization": f"Bearer {token_b}"}).json()

    assert bot_a["id"] != bot_b["id"]
    assert bot_a["public_id"] != bot_b["public_id"]


def test_lead_form_is_scoped_per_company(db_conn):
    client = _client()
    token_a = _signup_verify_login(client, "tenant-lead-a@example.com", db_conn)
    token_b = _signup_verify_login(client, "tenant-lead-b@example.com", db_conn)

    client.post(
        "/api/v1/sources/text",
        json={"title": "trigger bot A", "text": "content"},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    # B has no bot/lead form yet -- must not somehow see A's.
    r = client.get("/api/v1/bot/lead-form", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 404

    r2 = client.get("/api/v1/bot/lead-form", headers={"Authorization": f"Bearer {token_a}"})
    assert r2.status_code == 200
    assert {f["field_key"] for f in r2.json()["fields"]} == {"name", "email"}
