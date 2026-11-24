"""Phase 4 gate: draft optimistic concurrency and publish-time validation
(docs/02-ACCEPTANCE.md: "PATCH uses draft revision conflict control",
"Publish requires a ready selected source", "Publication stores a
consistent snapshot").

Requires TEST_DATABASE_URL pointed at a disposable, migrated database.
"""
from fastapi.testclient import TestClient


def _client():
    from app.main import app

    return TestClient(app)


def _consume_latest_verify_token(db_conn, email: str) -> str:
    from app.auth import service

    user = service.get_user_by_email(db_conn, email)
    token = service._create_auth_token(db_conn, user["id"], "verify_email", 3600)  # noqa: SLF001
    db_conn.commit()
    return token


def _signup_verify_login(client, email: str, db_conn) -> str:
    client.post("/api/v1/auth/signup", json={"email": email, "password": "correct-horse-battery", "name": "T"})
    raw_token = _consume_latest_verify_token(db_conn, email)
    client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    return login.json()["session_token"]


def test_publish_rejects_when_no_sources_ready(db_conn):
    client = _client()
    token = _signup_verify_login(client, "publish-noready@example.com", db_conn)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/v1/sources/text",
        json={"title": "Not ready yet", "text": "content"},
        headers=headers,
    )
    document_id = created.json()["document_id"]
    version_row = db_conn.execute(
        "SELECT id FROM document_versions WHERE document_id = %s", (document_id,)
    ).fetchone()

    # Still 'pending' -- never force it to ready here.
    r = client.post(
        "/api/v1/bot/publish",
        json={"selected_document_version_ids": [str(version_row["id"])]},
        headers=headers,
    )
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "source_not_ready"


def test_publish_creates_immutable_snapshot_unaffected_by_later_draft_edits(db_conn):
    client = _client()
    token = _signup_verify_login(client, "publish-snapshot@example.com", db_conn)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/v1/sources/text",
        json={"title": "Ready doc", "text": "content for snapshot test"},
        headers=headers,
    )
    document_id = created.json()["document_id"]
    version_row = db_conn.execute(
        "SELECT id FROM document_versions WHERE document_id = %s", (document_id,)
    ).fetchone()
    version_id = str(version_row["id"])
    db_conn.execute("UPDATE document_versions SET status = 'ready' WHERE id = %s", (version_id,))
    db_conn.commit()

    bot_before = client.get("/api/v1/bot", headers=headers).json()
    client.patch(
        "/api/v1/bot",
        json={"draft_revision": bot_before["draft_revision"], "config_patch": {"instructions": "Original instructions"}},
        headers=headers,
    )

    publish = client.post(
        "/api/v1/bot/publish",
        json={"selected_document_version_ids": [version_id]},
        headers=headers,
    )
    assert publish.status_code == 201
    publication_id = publish.json()["publication_id"]

    snapshot = db_conn.execute(
        "SELECT config_snapshot FROM publications WHERE id = %s", (publication_id,)
    ).fetchone()
    assert snapshot["config_snapshot"]["instructions"] == "Original instructions"

    # Now edit the draft again -- the already-created publication snapshot must not change.
    bot_after_publish = client.get("/api/v1/bot", headers=headers).json()
    client.patch(
        "/api/v1/bot",
        json={"draft_revision": bot_after_publish["draft_revision"], "config_patch": {"instructions": "Changed after publish"}},
        headers=headers,
    )

    snapshot_again = db_conn.execute(
        "SELECT config_snapshot FROM publications WHERE id = %s", (publication_id,)
    ).fetchone()
    assert snapshot_again["config_snapshot"]["instructions"] == "Original instructions"


def test_draft_patch_rejects_stale_revision(db_conn):
    client = _client()
    token = _signup_verify_login(client, "draft-conflict@example.com", db_conn)
    headers = {"Authorization": f"Bearer {token}"}

    client.post(
        "/api/v1/sources/text",
        json={"title": "trigger bot creation", "text": "content"},
        headers=headers,
    )
    bot = client.get("/api/v1/bot", headers=headers).json()
    current_revision = bot["draft_revision"]

    first = client.patch(
        "/api/v1/bot",
        json={"draft_revision": current_revision, "config_patch": {"tone": "friendly"}},
        headers=headers,
    )
    assert first.status_code == 200

    # Retry with the now-stale revision -- must be rejected, not silently applied.
    stale_retry = client.patch(
        "/api/v1/bot",
        json={"draft_revision": current_revision, "config_patch": {"tone": "formal"}},
        headers=headers,
    )
    assert stale_retry.status_code == 409
    assert stale_retry.json()["detail"]["code"] == "draft_revision_conflict"


def test_unpublish_clears_active_publication(db_conn):
    client = _client()
    token = _signup_verify_login(client, "unpublish-test@example.com", db_conn)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/api/v1/sources/text",
        json={"title": "Unpublish doc", "text": "content"},
        headers=headers,
    )
    document_id = created.json()["document_id"]
    version_row = db_conn.execute(
        "SELECT id FROM document_versions WHERE document_id = %s", (document_id,)
    ).fetchone()
    version_id = str(version_row["id"])
    db_conn.execute("UPDATE document_versions SET status = 'ready' WHERE id = %s", (version_id,))
    db_conn.commit()

    client.post("/api/v1/bot/publish", json={"selected_document_version_ids": [version_id]}, headers=headers)
    bot_published = client.get("/api/v1/bot", headers=headers).json()
    assert bot_published["active_publication_id"] is not None

    client.post("/api/v1/bot/unpublish", headers=headers)
    bot_unpublished = client.get("/api/v1/bot", headers=headers).json()
    assert bot_unpublished["active_publication_id"] is None
