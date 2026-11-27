"""app/jobs/executors.py::check_source_for_changes_executor (D3.5) against
a real Postgres connection -- only the network fetch (has_changed) is
faked (docs/11-AGENT-RULES rule 6); refresh_document's new-version +
enqueue path runs for real."""
import uuid

import pytest

from app.jobs.executors import check_source_for_changes_executor
from app.jobs.runner import PermanentJobError


def _make_company_and_bot(conn) -> tuple[str, str]:
    user = conn.execute(
        "INSERT INTO users (normalized_email, email, name) VALUES (%s, %s, %s) RETURNING id",
        (f"{uuid.uuid4()}@example.com", "executortest@example.com", "Executor Tester"),
    ).fetchone()
    company = conn.execute(
        "INSERT INTO companies (owner_user_id, name) VALUES (%s, %s) RETURNING id", (user["id"], "Executor Test Co")
    ).fetchone()
    bot = conn.execute(
        "INSERT INTO bots (company_id, public_id) VALUES (%s, %s) RETURNING id", (company["id"], str(uuid.uuid4()))
    ).fetchone()
    return str(company["id"]), str(bot["id"])


def _make_url_document(conn, company_id, bot_id, source_checksum=None) -> str:
    doc = conn.execute(
        "INSERT INTO documents (company_id, bot_id, kind, title, source_url, source_checksum) VALUES (%s, %s, 'url', 'Doc', 'https://example.com', %s) RETURNING id",
        (company_id, bot_id, source_checksum),
    ).fetchone()
    conn.execute("INSERT INTO document_versions (document_id, version, status) VALUES (%s, 1, 'ready')", (doc["id"],))
    return str(doc["id"])


def test_unchanged_updates_checked_timestamp_without_new_version(db_conn, monkeypatch):
    company_id, bot_id = _make_company_and_bot(db_conn)
    document_id = _make_url_document(db_conn, company_id, bot_id, source_checksum="same-hash")

    monkeypatch.setattr("app.ingestion.change_detection.has_changed", lambda doc: (False, "same-hash"))

    job = {"company_id": company_id, "checkpoint_ref": {"document_id": document_id}}
    check_source_for_changes_executor(db_conn, job, heartbeat=lambda: True)

    row = db_conn.execute(
        "SELECT last_checked_at, source_checksum FROM documents WHERE id = %s", (document_id,)
    ).fetchone()
    assert row["last_checked_at"] is not None
    assert row["source_checksum"] == "same-hash"

    versions = db_conn.execute(
        "SELECT count(*) AS n FROM document_versions WHERE document_id = %s", (document_id,)
    ).fetchone()
    assert versions["n"] == 1  # no new version created


def test_changed_creates_new_version_and_enqueues_ingest(db_conn, monkeypatch):
    company_id, bot_id = _make_company_and_bot(db_conn)
    document_id = _make_url_document(db_conn, company_id, bot_id, source_checksum="old-hash")

    monkeypatch.setattr("app.ingestion.change_detection.has_changed", lambda doc: (True, "new-hash"))

    job = {"company_id": company_id, "checkpoint_ref": {"document_id": document_id}}
    check_source_for_changes_executor(db_conn, job, heartbeat=lambda: True)

    row = db_conn.execute("SELECT source_checksum FROM documents WHERE id = %s", (document_id,)).fetchone()
    assert row["source_checksum"] == "new-hash"

    versions = db_conn.execute(
        "SELECT version FROM document_versions WHERE document_id = %s ORDER BY version", (document_id,)
    ).fetchall()
    assert [v["version"] for v in versions] == [1, 2]

    jobs = db_conn.execute("SELECT kind FROM jobs WHERE company_id = %s", (company_id,)).fetchall()
    assert any(j["kind"] == "ingest_document" for j in jobs)


def test_missing_document_raises_permanent_error(db_conn):
    company_id, _bot_id = _make_company_and_bot(db_conn)
    job = {"company_id": company_id, "checkpoint_ref": {"document_id": str(uuid.uuid4())}}

    with pytest.raises(PermanentJobError):
        check_source_for_changes_executor(db_conn, job, heartbeat=lambda: True)


def test_non_url_document_raises_permanent_error(db_conn):
    company_id, bot_id = _make_company_and_bot(db_conn)
    doc = db_conn.execute(
        "INSERT INTO documents (company_id, bot_id, kind, title) VALUES (%s, %s, 'text', 'Doc') RETURNING id",
        (company_id, bot_id),
    ).fetchone()

    job = {"company_id": company_id, "checkpoint_ref": {"document_id": str(doc["id"])}}
    with pytest.raises(PermanentJobError):
        check_source_for_changes_executor(db_conn, job, heartbeat=lambda: True)
