"""Event outbox + dispatch_event executor (ADR 003,
alembic/versions/0013_event_outbox.py). Verifies emit_event() is
idempotent on (company_id, topic, payload_hash), the executor fans out to
webhook_deliveries only for subscribed/scoped endpoints, is itself
idempotent on re-run, and that the real public API (conversation start)
actually produces a dispatchable event end-to-end.
"""
import secrets
import uuid

import psycopg
import pytest

from app.events.outbox import emit_event
from app.jobs.executors import dispatch_event_executor
from app.jobs.runner import claim_next_job

from test.api.test_chat_and_lifecycle import (  # noqa: F401 -- client/llm_calls are fixtures resolved by name
    client,
    llm_calls,
    seed_published_bot,
    signup,
    visitor,
)


@pytest.fixture(autouse=True)
def _clean_job_queue(test_database_url):
    """Same rationale as test_job_runner.py's fixture of the same name:
    this file's claim_next_job() calls need a quiescent queue, which
    sibling test files (real, committed HTTP-path jobs) can't guarantee."""
    with psycopg.connect(test_database_url, autocommit=True) as conn:
        conn.execute("DELETE FROM job_attempts")
        conn.execute("DELETE FROM jobs")
    yield


def _make_company_and_bot(conn) -> tuple[str, str]:
    user = conn.execute(
        "INSERT INTO users (normalized_email, email, name) VALUES (%s, %s, %s) RETURNING id",
        (f"{uuid.uuid4()}@example.com", "outboxtest@example.com", "Outbox Tester"),
    ).fetchone()
    company = conn.execute(
        "INSERT INTO companies (owner_user_id, name) VALUES (%s, %s) RETURNING id",
        (user["id"], "Outbox Test Co"),
    ).fetchone()
    company_id = str(company["id"])
    bot = conn.execute(
        "INSERT INTO bots (company_id, public_id) VALUES (%s, %s) RETURNING id",
        (company_id, secrets.token_urlsafe(8)),
    ).fetchone()
    return company_id, str(bot["id"])


def _make_endpoint(conn, company_id: str, events: list[str], bot_id: str | None = None) -> str:
    row = conn.execute(
        """
        INSERT INTO webhook_endpoints (company_id, bot_id, url, secret, events, is_active)
        VALUES (%s, %s, 'https://example.com/hook', %s, %s, true) RETURNING id
        """,
        (company_id, bot_id, secrets.token_urlsafe(16), events),
    ).fetchone()
    return str(row["id"])


def test_emit_event_is_idempotent_on_identical_payload(db_conn):
    company_id, bot_id = _make_company_and_bot(db_conn)
    payload = {"conversation_id": str(uuid.uuid4())}

    first_id = emit_event(db_conn, company_id, "conversation.started", payload, bot_id=bot_id)
    second_id = emit_event(db_conn, company_id, "conversation.started", payload, bot_id=bot_id)

    assert first_id is not None
    assert second_id is None  # already recorded -- no duplicate row, no duplicate dispatch job

    count = db_conn.execute(
        "SELECT count(*) AS n FROM event_outbox WHERE id = %s", (first_id,)
    ).fetchone()["n"]
    assert count == 1

    job_count = db_conn.execute(
        "SELECT count(*) AS n FROM jobs WHERE kind = 'dispatch_event' AND company_id = %s", (company_id,)
    ).fetchone()["n"]
    assert job_count == 1


def test_dispatch_event_executor_creates_delivery_for_matching_endpoint(db_conn):
    company_id, bot_id = _make_company_and_bot(db_conn)
    endpoint_id = _make_endpoint(db_conn, company_id, ["conversation.started"])

    event_id = emit_event(db_conn, company_id, "conversation.started", {"conversation_id": "abc"}, bot_id=bot_id)
    job = claim_next_job(db_conn, lease_seconds=300)
    assert job["kind"] == "dispatch_event"

    dispatch_event_executor(db_conn, job, lambda: True)

    delivery = db_conn.execute(
        "SELECT event_type, payload, endpoint_id FROM webhook_deliveries WHERE event_outbox_id = %s", (event_id,)
    ).fetchone()
    assert delivery is not None
    assert delivery["event_type"] == "conversation.started"
    assert str(delivery["endpoint_id"]) == endpoint_id
    assert delivery["payload"]["conversation_id"] == "abc"

    dispatched_at = db_conn.execute(
        "SELECT dispatched_at FROM event_outbox WHERE id = %s", (event_id,)
    ).fetchone()["dispatched_at"]
    assert dispatched_at is not None


def test_dispatch_event_executor_skips_endpoint_not_subscribed_to_topic(db_conn):
    company_id, bot_id = _make_company_and_bot(db_conn)
    _make_endpoint(db_conn, company_id, ["lead.submitted"])  # subscribed to a different topic

    event_id = emit_event(db_conn, company_id, "conversation.started", {"conversation_id": "abc"}, bot_id=bot_id)
    job = claim_next_job(db_conn, lease_seconds=300)
    dispatch_event_executor(db_conn, job, lambda: True)

    count = db_conn.execute(
        "SELECT count(*) AS n FROM webhook_deliveries WHERE event_outbox_id = %s", (event_id,)
    ).fetchone()["n"]
    assert count == 0


def test_dispatch_event_executor_respects_endpoint_bot_scoping(db_conn):
    company_id, bot_id = _make_company_and_bot(db_conn)
    other_bot_id = str(
        db_conn.execute(
            "INSERT INTO bots (company_id, public_id) VALUES (%s, %s) RETURNING id",
            (company_id, secrets.token_urlsafe(8)),
        ).fetchone()["id"]
    )
    _make_endpoint(db_conn, company_id, ["conversation.started"], bot_id=other_bot_id)

    event_id = emit_event(db_conn, company_id, "conversation.started", {"conversation_id": "abc"}, bot_id=bot_id)
    job = claim_next_job(db_conn, lease_seconds=300)
    dispatch_event_executor(db_conn, job, lambda: True)

    count = db_conn.execute(
        "SELECT count(*) AS n FROM webhook_deliveries WHERE event_outbox_id = %s", (event_id,)
    ).fetchone()["n"]
    assert count == 0  # endpoint is scoped to a different bot


def test_dispatch_event_executor_is_idempotent_on_rerun(db_conn):
    company_id, bot_id = _make_company_and_bot(db_conn)
    _make_endpoint(db_conn, company_id, ["conversation.started"])

    event_id = emit_event(db_conn, company_id, "conversation.started", {"conversation_id": "abc"}, bot_id=bot_id)
    job = claim_next_job(db_conn, lease_seconds=300)

    dispatch_event_executor(db_conn, job, lambda: True)
    dispatch_event_executor(db_conn, job, lambda: True)  # simulates a retried job after a crash

    count = db_conn.execute(
        "SELECT count(*) AS n FROM webhook_deliveries WHERE event_outbox_id = %s", (event_id,)
    ).fetchone()["n"]
    assert count == 1


def test_conversation_started_emits_dispatchable_event_through_real_http_flow(client, db_conn, llm_calls):
    headers = signup(client, db_conn, f"outbox-e2e-{uuid.uuid4().hex[:6]}@example.com")
    bot = seed_published_bot(client, db_conn, headers)

    endpoint = client.post(
        "/api/v1/webhooks/endpoints",
        json={"url": "https://example.com/hook", "events": ["conversation.started"]},
        headers=headers,
    )
    assert endpoint.status_code == 201, endpoint.text

    vh = visitor(client, bot["public_id"])
    conv = client.post("/api/v1/public/conversations", headers=vh)
    assert conv.status_code == 201, conv.text
    conversation_id = conv.json()["conversation_id"]

    # seed_published_bot's own source-upload step enqueues a real
    # ingest_document job ahead of ours in the queue -- drain until the
    # dispatch_event job created by conversation creation turns up.
    job = None
    for _ in range(5):
        candidate = claim_next_job(db_conn, lease_seconds=300)
        assert candidate is not None
        if candidate["kind"] == "dispatch_event":
            job = candidate
            break
    assert job is not None, "dispatch_event job never surfaced"
    dispatch_event_executor(db_conn, job, lambda: True)

    delivery = db_conn.execute(
        "SELECT payload FROM webhook_deliveries WHERE endpoint_id = %s", (endpoint.json()["id"],)
    ).fetchone()
    assert delivery is not None
    assert delivery["payload"]["conversation_id"] == conversation_id
