"""Phase 3 gate (docs/19-BACKEND-SPRINT-PLAN-V2.md): a document version may
only be considered ready when the chunk manifest matches the vector
store's own confirmed count. Embedding/vector-store calls are fakes --
never a live Cloudflare/Pinecone call, per docs/11-AGENT-RULES.md rule 6.

Requires TEST_DATABASE_URL pointed at a disposable, migrated database
(migrations 0001 + 0002 applied). Skipped entirely otherwise.
"""
import uuid

import pytest

from app.ingestion.pipeline import run_ingestion
from app.jobs.runner import PermanentJobError, TransientJobError


@pytest.fixture()
def storage_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PRIVATE_STORAGE_DIR", str(tmp_path))
    from app.config import settings

    settings.cache_clear()
    yield tmp_path


def _make_company_and_bot(conn) -> tuple[str, str]:
    user = conn.execute(
        "INSERT INTO users (normalized_email, email, name) VALUES (%s, %s, %s) RETURNING id",
        (f"{uuid.uuid4()}@example.com", "pipelinetest@example.com", "Pipeline Tester"),
    ).fetchone()
    company = conn.execute(
        "INSERT INTO companies (owner_user_id, name) VALUES (%s, %s) RETURNING id",
        (user["id"], "Pipeline Test Co"),
    ).fetchone()
    bot = conn.execute(
        "INSERT INTO bots (company_id, public_id) VALUES (%s, %s) RETURNING id",
        (company["id"], str(uuid.uuid4())),
    ).fetchone()
    return str(company["id"]), str(bot["id"])


def _make_text_document(conn, company_id: str, bot_id: str, content: str) -> tuple[dict, dict]:
    from app.storage import local as storage

    document = conn.execute(
        "INSERT INTO documents (company_id, bot_id, kind, title) VALUES (%s, %s, 'text', 'Test doc') RETURNING *",
        (company_id, bot_id),
    ).fetchone()
    version = conn.execute(
        "INSERT INTO document_versions (document_id, version) VALUES (%s, 1) RETURNING *",
        (document["id"],),
    ).fetchone()

    result = storage.write_text_content(company_id, str(document["id"]), 1, content, suffix=".txt")
    conn.execute("UPDATE documents SET storage_key = %s WHERE id = %s", (result["storage_key"], document["id"]))

    document = conn.execute("SELECT * FROM documents WHERE id = %s", (document["id"],)).fetchone()
    return document, version


def _fake_embed(texts: list[str]) -> list[list[float]]:
    return [[0.1, 0.2, 0.3] for _ in texts]


def _fake_upsert_matching(**kwargs) -> int:
    return len(kwargs["chunks"])


def _fake_upsert_dropping_one(**kwargs) -> int:
    return len(kwargs["chunks"]) - 1  # simulates a vector silently lost mid-upsert


def _fake_reconcile_match(company_id, version_id, expected_count) -> bool:
    return True


def _fake_reconcile_mismatch(company_id, version_id, expected_count) -> bool:
    return False  # simulates Pinecone's own recount disagreeing with the upsert response


def test_happy_path_produces_matching_chunk_manifest(db_conn, storage_dir):
    company_id, bot_id = _make_company_and_bot(db_conn)
    document, version = _make_text_document(
        db_conn,
        company_id,
        bot_id,
        "This is the first line of content.\nThis is the second line of content.",
    )

    chunk_count = run_ingestion(
        conn=db_conn,
        document=document,
        document_version=version,
        embed_fn=_fake_embed,
        upsert_fn=_fake_upsert_matching,
        reconcile_fn=_fake_reconcile_match,
        heartbeat=lambda: True,
    )

    assert chunk_count > 0
    row = db_conn.execute("SELECT count(*) AS n FROM chunks WHERE version_id = %s", (version["id"],)).fetchone()
    assert row["n"] == chunk_count


def test_upsert_count_mismatch_blocks_ready_with_transient_error(db_conn, storage_dir):
    """Simulates a dropped vector mid-upsert (e.g. a crash between
    sending and confirming). Must never let the version become ready."""
    company_id, bot_id = _make_company_and_bot(db_conn)
    document, version = _make_text_document(db_conn, company_id, bot_id, "Some content for testing purposes.")

    with pytest.raises(TransientJobError) as exc_info:
        run_ingestion(
            conn=db_conn,
            document=document,
            document_version=version,
            embed_fn=_fake_embed,
            upsert_fn=_fake_upsert_dropping_one,
            reconcile_fn=_fake_reconcile_match,
            heartbeat=lambda: True,
        )
    assert exc_info.value.error_code == "chunk_manifest_mismatch_upsert_response"


def test_independent_reconciliation_mismatch_also_blocks_ready(db_conn, storage_dir):
    """Even if the upsert call itself reports success, an independent
    recount disagreeing must still block readiness -- this is what makes
    reconciliation a real second check, not a rubber stamp."""
    company_id, bot_id = _make_company_and_bot(db_conn)
    document, version = _make_text_document(db_conn, company_id, bot_id, "Some content for testing purposes.")

    with pytest.raises(TransientJobError) as exc_info:
        run_ingestion(
            conn=db_conn,
            document=document,
            document_version=version,
            embed_fn=_fake_embed,
            upsert_fn=_fake_upsert_matching,
            reconcile_fn=_fake_reconcile_mismatch,
            heartbeat=lambda: True,
        )
    assert exc_info.value.error_code == "chunk_manifest_mismatch_reconciliation"


def test_empty_content_is_permanent_not_endlessly_retried(db_conn, storage_dir):
    company_id, bot_id = _make_company_and_bot(db_conn)
    document, version = _make_text_document(db_conn, company_id, bot_id, "   ")  # whitespace only

    with pytest.raises(PermanentJobError):
        run_ingestion(
            conn=db_conn,
            document=document,
            document_version=version,
            embed_fn=_fake_embed,
            upsert_fn=_fake_upsert_matching,
            reconcile_fn=_fake_reconcile_match,
            heartbeat=lambda: True,
        )


def test_heartbeat_is_called_during_a_run(db_conn, storage_dir):
    company_id, bot_id = _make_company_and_bot(db_conn)
    document, version = _make_text_document(db_conn, company_id, bot_id, "Content for heartbeat verification.")

    calls = []
    run_ingestion(
        conn=db_conn,
        document=document,
        document_version=version,
        embed_fn=_fake_embed,
        upsert_fn=_fake_upsert_matching,
        reconcile_fn=_fake_reconcile_match,
        heartbeat=lambda: calls.append(1) or True,
    )
    assert len(calls) >= 3  # extract, chunk, embed, insert, upsert stages each beat at least once
