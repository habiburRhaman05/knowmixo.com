"""Stripe webhook ingestion (ADR 008, launch/09-BILLING-PAYMENTS.md §4,
app/billing/router.py). Verifies real HMAC signature construction/
verification (Stripe's documented scheme -- a per-test secret here, not a
mock of the verification code itself) and the Day 2 gate requirement:
"Stripe webhook idempotency test passes" -- the same event_id delivered
twice must not produce two stripe_events rows.
"""
import hashlib
import hmac
import json
import time
import uuid

import pytest
from fastapi.testclient import TestClient

TEST_WEBHOOK_SECRET = "whsec_test_" + "a" * 32


@pytest.fixture
def client():
    from app.main import app

    return TestClient(app)


@pytest.fixture(autouse=True)
def _configure_stripe_secret(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings(), "stripe_webhook_secret", TEST_WEBHOOK_SECRET)


def _sign(payload: bytes, secret: str = TEST_WEBHOOK_SECRET, timestamp: int | None = None) -> str:
    """Replicates Stripe's documented webhook signing scheme exactly
    (https://docs.stripe.com/webhooks#verify-manually): this proves the
    real verification code path in app/billing/router.py, not a stub of it."""
    ts = timestamp if timestamp is not None else int(time.time())
    signed_payload = f"{ts}.{payload.decode()}"
    signature = hmac.new(secret.encode(), signed_payload.encode(), hashlib.sha256).hexdigest()
    return f"t={ts},v1={signature}"


def _event_payload(event_id: str, event_type: str = "customer.subscription.created") -> bytes:
    return json.dumps(
        {
            "id": event_id,
            "object": "event",
            "type": event_type,
            "created": int(time.time()),
            "data": {"object": {"id": "sub_test123", "status": "active"}},
        }
    ).encode()


def _row_count(db_conn, event_id: str) -> int:
    return db_conn.execute(
        "SELECT count(*) AS n FROM stripe_events WHERE event_id = %s", (event_id,)
    ).fetchone()["n"]


def test_valid_signature_is_accepted_and_recorded(client, db_conn):
    event_id = f"evt_{uuid.uuid4().hex[:16]}"
    payload = _event_payload(event_id)

    r = client.post(
        "/api/v1/webhooks/stripe",
        content=payload,
        headers={"Stripe-Signature": _sign(payload), "Content-Type": "application/json"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"received": True}
    assert _row_count(db_conn, event_id) == 1


def test_same_event_id_delivered_twice_is_idempotent(client, db_conn):
    event_id = f"evt_{uuid.uuid4().hex[:16]}"
    payload = _event_payload(event_id)
    headers = {"Stripe-Signature": _sign(payload), "Content-Type": "application/json"}

    r1 = client.post("/api/v1/webhooks/stripe", content=payload, headers=headers)
    r2 = client.post("/api/v1/webhooks/stripe", content=payload, headers=headers)

    assert r1.status_code == 200
    assert r2.status_code == 200  # Stripe redelivers on any non-2xx -- both must succeed
    assert _row_count(db_conn, event_id) == 1  # exactly one row despite two deliveries


def test_tampered_payload_fails_signature_verification(client):
    event_id = f"evt_{uuid.uuid4().hex[:16]}"
    payload = _event_payload(event_id)
    signature = _sign(payload)  # signed over the original payload
    tampered = payload.replace(b"active", b"canceled")  # body changed after signing

    r = client.post(
        "/api/v1/webhooks/stripe",
        content=tampered,
        headers={"Stripe-Signature": signature, "Content-Type": "application/json"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_signature"


def test_wrong_secret_fails_signature_verification(client):
    event_id = f"evt_{uuid.uuid4().hex[:16]}"
    payload = _event_payload(event_id)

    r = client.post(
        "/api/v1/webhooks/stripe",
        content=payload,
        headers={"Stripe-Signature": _sign(payload, secret="whsec_wrong_" + "b" * 32), "Content-Type": "application/json"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "invalid_signature"


def test_missing_signature_header_is_rejected(client):
    payload = _event_payload(f"evt_{uuid.uuid4().hex[:16]}")
    r = client.post("/api/v1/webhooks/stripe", content=payload, headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "missing_signature"


def test_missing_webhook_secret_is_a_loud_503_not_a_silent_accept(client, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings(), "stripe_webhook_secret", "")
    payload = _event_payload(f"evt_{uuid.uuid4().hex[:16]}")

    r = client.post(
        "/api/v1/webhooks/stripe",
        content=payload,
        headers={"Stripe-Signature": _sign(payload), "Content-Type": "application/json"},
    )
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "stripe_not_configured"
