"""app/jobs/change_detection_sweep.py's SQL selection logic (D3.5) against
a real Postgres connection -- the WHERE clause (interval elapsed,
excludes disabled/deleted/non-url sources) is exactly the kind of thing
worth proving against the real engine."""
import uuid

from app.jobs.change_detection_sweep import find_due_documents


def _make_company_and_bot(conn) -> tuple[str, str]:
    user = conn.execute(
        "INSERT INTO users (normalized_email, email, name) VALUES (%s, %s, %s) RETURNING id",
        (f"{uuid.uuid4()}@example.com", "sweeptest@example.com", "Sweep Tester"),
    ).fetchone()
    company = conn.execute(
        "INSERT INTO companies (owner_user_id, name) VALUES (%s, %s) RETURNING id", (user["id"], "Sweep Test Co")
    ).fetchone()
    bot = conn.execute(
        "INSERT INTO bots (company_id, public_id) VALUES (%s, %s) RETURNING id", (company["id"], str(uuid.uuid4()))
    ).fetchone()
    return str(company["id"]), str(bot["id"])


def _make_document(conn, company_id, bot_id, **overrides) -> str:
    fields = {
        "source_url": "https://example.com/page",
        "check_interval_hours": None,
        "last_checked_at": None,
        "disabled_at": None,
        "deleted_at": None,
        **overrides,
    }
    row = conn.execute(
        """
        INSERT INTO documents (company_id, bot_id, kind, title, source_url, check_interval_hours, last_checked_at, disabled_at, deleted_at)
        VALUES (%s, %s, 'url', 'Doc', %s, %s, %s, %s, %s) RETURNING id
        """,
        (company_id, bot_id, fields["source_url"], fields["check_interval_hours"], fields["last_checked_at"], fields["disabled_at"], fields["deleted_at"]),
    ).fetchone()
    return str(row["id"])


def test_no_interval_set_is_never_due(db_conn):
    company_id, bot_id = _make_company_and_bot(db_conn)
    _make_document(db_conn, company_id, bot_id, check_interval_hours=None)

    due = find_due_documents(db_conn)
    assert due == []


def test_never_checked_with_interval_set_is_due(db_conn):
    company_id, bot_id = _make_company_and_bot(db_conn)
    doc_id = _make_document(db_conn, company_id, bot_id, check_interval_hours=24, last_checked_at=None)

    due_ids = [str(d["id"]) for d in find_due_documents(db_conn)]
    assert doc_id in due_ids


def test_recently_checked_is_not_due(db_conn):
    company_id, bot_id = _make_company_and_bot(db_conn)
    doc_id = _make_document(db_conn, company_id, bot_id, check_interval_hours=24)
    db_conn.execute("UPDATE documents SET last_checked_at = now() WHERE id = %s", (doc_id,))

    due_ids = [str(d["id"]) for d in find_due_documents(db_conn)]
    assert doc_id not in due_ids


def test_elapsed_interval_is_due(db_conn):
    company_id, bot_id = _make_company_and_bot(db_conn)
    doc_id = _make_document(db_conn, company_id, bot_id, check_interval_hours=1)
    db_conn.execute("UPDATE documents SET last_checked_at = now() - interval '2 hours' WHERE id = %s", (doc_id,))

    due_ids = [str(d["id"]) for d in find_due_documents(db_conn)]
    assert doc_id in due_ids


def test_disabled_document_is_excluded(db_conn):
    import datetime

    company_id, bot_id = _make_company_and_bot(db_conn)
    doc_id = _make_document(
        db_conn, company_id, bot_id, check_interval_hours=24, disabled_at=datetime.datetime.now(datetime.timezone.utc)
    )

    due_ids = [str(d["id"]) for d in find_due_documents(db_conn)]
    assert doc_id not in due_ids


def test_deleted_document_is_excluded(db_conn):
    import datetime

    company_id, bot_id = _make_company_and_bot(db_conn)
    doc_id = _make_document(
        db_conn, company_id, bot_id, check_interval_hours=24, deleted_at=datetime.datetime.now(datetime.timezone.utc)
    )

    due_ids = [str(d["id"]) for d in find_due_documents(db_conn)]
    assert doc_id not in due_ids


def test_non_url_document_is_excluded(db_conn):
    company_id, bot_id = _make_company_and_bot(db_conn)
    doc = db_conn.execute(
        "INSERT INTO documents (company_id, bot_id, kind, title, check_interval_hours) VALUES (%s, %s, 'text', 'Doc', 24) RETURNING id",
        (company_id, bot_id),
    ).fetchone()

    due_ids = [str(d["id"]) for d in find_due_documents(db_conn)]
    assert str(doc["id"]) not in due_ids
