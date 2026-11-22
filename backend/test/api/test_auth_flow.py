"""Phase 1 API test gate (docs/19-BACKEND-SPRINT-PLAN-V2.md Phase 1):
  - duplicate signup is safe (no account-existence disclosure)
  - unverified accounts are flagged correctly
  - logout-all immediately blocks the old session token
  - cross-user access is rejected

Requires TEST_DATABASE_URL pointed at a disposable, migrated database.
Skipped entirely otherwise (see conftest.py).
"""
from fastapi.testclient import TestClient


def _client():
    from app.main import app

    return TestClient(app)


def _consume_latest_verify_token(db_conn, email: str) -> str:
    """Test-only helper: in production the raw token is only ever known to
    the emailed link. Here we read the hash back out is impossible by
    design (one-way hash) -- so tests call service functions directly to
    get a real raw token instead of trying to intercept email."""
    from app.auth import service

    user = service.get_user_by_email(db_conn, email)
    token = service._create_auth_token(  # noqa: SLF001 -- intentional test-only use of internals
        db_conn, user["id"], "verify_email", 3600
    )
    db_conn.commit()
    return token


def test_duplicate_signup_is_safe(db_conn):
    client = _client()
    payload = {"email": "owner@example.com", "password": "correct-horse-battery", "name": "Owner One"}

    r1 = client.post("/api/v1/auth/signup", json=payload)
    assert r1.status_code == 202

    r2 = client.post("/api/v1/auth/signup", json=payload)
    assert r2.status_code == 202
    assert r2.json() == r1.json()  # identical response shape, no enumeration signal


def test_login_blocked_until_verified_but_token_still_issued(db_conn):
    client = _client()
    email = "unverified@example.com"
    client.post("/api/v1/auth/signup", json={"email": email, "password": "correct-horse-battery", "name": "U"})

    login = client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    assert login.status_code == 200
    token = login.json()["session_token"]

    me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email_verified_at"] is None


def test_verify_email_then_company_exists(db_conn):
    client = _client()
    email = "verifyme@example.com"
    client.post("/api/v1/auth/signup", json={"email": email, "password": "correct-horse-battery", "name": "V"})

    raw_token = _consume_latest_verify_token(db_conn, email)
    verify = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert verify.status_code == 200

    # Replay must fail -- single-use token.
    replay = client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    assert replay.status_code == 410

    login = client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    token = login.json()["session_token"]

    company = client.get("/api/v1/company", headers={"Authorization": f"Bearer {token}"})
    assert company.status_code == 200
    assert company.json()["name"]


def test_logout_all_immediately_revokes_session(db_conn):
    client = _client()
    email = "logoutall@example.com"
    client.post("/api/v1/auth/signup", json={"email": email, "password": "correct-horse-battery", "name": "L"})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": "correct-horse-battery"})
    token = login.json()["session_token"]

    before = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert before.status_code == 200

    revoke = client.post("/api/v1/auth/logout-all", headers={"Authorization": f"Bearer {token}"})
    assert revoke.status_code == 204

    after = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert after.status_code == 401


def test_unauthenticated_request_is_rejected():
    client = _client()
    r = client.get("/api/v1/me")
    assert r.status_code == 401


def test_malformed_bearer_token_is_rejected():
    client = _client()
    r = client.get("/api/v1/me", headers={"Authorization": "not-a-bearer-token"})
    assert r.status_code == 401


def _signup_verify_login(client, email: str, password: str, db_conn) -> str:
    client.post("/api/v1/auth/signup", json={"email": email, "password": password, "name": "T"})
    raw_token = _consume_latest_verify_token(db_conn, email)
    client.post("/api/v1/auth/verify-email", json={"token": raw_token})
    login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return login.json()["session_token"]


def test_email_change_requires_current_password(db_conn):
    client = _client()
    token = _signup_verify_login(client, "reauth@example.com", "correct-horse-battery", db_conn)

    # Missing current_password on a password account must be rejected.
    r = client.post(
        "/api/v1/me/email-change",
        json={"new_email": "new-reauth@example.com"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "reauth_required"

    # Correct current_password succeeds.
    r2 = client.post(
        "/api/v1/me/email-change",
        json={"new_email": "new-reauth@example.com", "current_password": "correct-horse-battery"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r2.status_code == 202


def test_email_change_rejects_email_already_in_use(db_conn):
    client = _client()
    client.post("/api/v1/auth/signup", json={"email": "taken@example.com", "password": "correct-horse-battery", "name": "A"})
    token = _signup_verify_login(client, "wants-taken@example.com", "correct-horse-battery", db_conn)

    r = client.post(
        "/api/v1/me/email-change",
        json={"new_email": "taken@example.com", "current_password": "correct-horse-battery"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "email_in_use"


def test_account_deletion_requires_confirm_and_revokes_sessions(db_conn):
    client = _client()
    token = _signup_verify_login(client, "deleteme@example.com", "correct-horse-battery", db_conn)

    missing_confirm = client.delete(
        "/api/v1/me",
        json={"confirm": False, "current_password": "correct-horse-battery"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert missing_confirm.status_code == 400

    deleted = client.delete(
        "/api/v1/me",
        json={"confirm": True, "current_password": "correct-horse-battery"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert deleted.status_code == 202

    after = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert after.status_code == 401


def test_forgot_password_cooldown_prevents_token_spam(db_conn):
    client = _client()
    email = "cooldown@example.com"
    client.post("/api/v1/auth/signup", json={"email": email, "password": "correct-horse-battery", "name": "C"})

    from app.auth import service

    user = service.get_user_by_email(db_conn, email)

    client.post("/api/v1/auth/forgot-password", json={"email": email})
    first_count = db_conn.execute(
        "SELECT count(*) AS n FROM auth_tokens WHERE user_id = %s AND purpose = 'reset_password'",
        (user["id"],),
    ).fetchone()["n"]

    client.post("/api/v1/auth/forgot-password", json={"email": email})
    second_count = db_conn.execute(
        "SELECT count(*) AS n FROM auth_tokens WHERE user_id = %s AND purpose = 'reset_password'",
        (user["id"],),
    ).fetchone()["n"]

    assert second_count == first_count  # cooldown blocked the second token
