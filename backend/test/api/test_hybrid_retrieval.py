"""Hybrid retrieval (D3.4, ADR 001): dense + FTS fused with RRF against a
real Postgres/pgvector connection -- the RRF SQL itself, tenant
isolation, version scoping and the language filter are exactly the kind
of subtle-correctness SQL that must be proven against the real engine,
not a mock.
"""
import uuid

import pytest

from app.chat.rag_v2.stages import retrieve as retrieve_module
from app.chat.rag_v2.stages.retrieve import retrieve_with_version_ids


@pytest.fixture(autouse=True)
def _fake_embeddings(monkeypatch):
    """The query vector is set by each test via this dict so dense
    similarity is under test control -- real Cloudflare calls are never
    made here (docs/11-AGENT-RULES rule 6)."""
    state = {"vector": [0.0] * 1024}
    monkeypatch.setattr(retrieve_module, "embed_batch", lambda texts: [state["vector"]])
    return state


def _make_company(conn, name="Retrieval Test Co") -> str:
    user = conn.execute(
        "INSERT INTO users (normalized_email, email, name) VALUES (%s, %s, %s) RETURNING id",
        (f"{uuid.uuid4()}@example.com", "retrievaltest@example.com", "Retrieval Tester"),
    ).fetchone()
    company = conn.execute(
        "INSERT INTO companies (owner_user_id, name) VALUES (%s, %s) RETURNING id", (user["id"], name)
    ).fetchone()
    return str(company["id"])


def _make_version(conn, company_id: str) -> str:
    bot = conn.execute(
        "INSERT INTO bots (company_id, public_id) VALUES (%s, %s) RETURNING id", (company_id, str(uuid.uuid4()))
    ).fetchone()
    document = conn.execute(
        "INSERT INTO documents (company_id, bot_id, kind, title) VALUES (%s, %s, 'text', 'Doc') RETURNING id",
        (company_id, bot["id"]),
    ).fetchone()
    version = conn.execute(
        "INSERT INTO document_versions (document_id, version, status) VALUES (%s, 1, 'ready') RETURNING id",
        (document["id"],),
    ).fetchone()
    return str(version["id"])


def _make_chunk(conn, company_id: str, version_id: str, text: str, vector: list[float], language: str = "en", heading=None):
    ordinal = conn.execute("SELECT COALESCE(MAX(ordinal) + 1, 0) AS n FROM chunks WHERE version_id = %s", (version_id,)).fetchone()["n"]
    conn.execute(
        """
        INSERT INTO chunks (version_id, company_id, ordinal, text, heading, vector_id, checksum, embedding, language)
        VALUES (%s, %s, %s, %s, %s, %s, 'checksum', %s, %s)
        """,
        (version_id, company_id, ordinal, text, heading, str(uuid.uuid4()), vector, language),
    )


def _vec(seed: float) -> list[float]:
    """A 1024-dim vector that's trivially distinguishable by cosine
    similarity: all dims equal `seed`, so two vectors with the same seed
    are identical and vectors with different seeds point differently."""
    return [seed] * 1024


def test_dense_similarity_ranks_the_matching_chunk_first(db_conn, _fake_embeddings):
    company_id = _make_company(db_conn)
    version_id = _make_version(db_conn, company_id)
    _make_chunk(db_conn, company_id, version_id, "cats are great pets", _vec(1.0))
    _make_chunk(db_conn, company_id, version_id, "unrelated content about spreadsheets", _vec(-1.0))
    db_conn.commit()

    _fake_embeddings["vector"] = _vec(1.0)  # query vector matches the first chunk exactly
    results = retrieve_with_version_ids(db_conn, company_id, [version_id], "something")

    assert results[0].text == "cats are great pets"
    assert results[0].score_dense > results[1].score_dense


def test_fts_matches_contribute_even_with_a_neutral_query_vector(db_conn, _fake_embeddings):
    company_id = _make_company(db_conn)
    version_id = _make_version(db_conn, company_id)
    _make_chunk(db_conn, company_id, version_id, "our refund policy is thirty days", _vec(0.5))
    _make_chunk(db_conn, company_id, version_id, "completely different unrelated filler text", _vec(0.5))
    db_conn.commit()

    _fake_embeddings["vector"] = _vec(0.5)  # identical dense similarity for both -- FTS must break the tie
    results = retrieve_with_version_ids(db_conn, company_id, [version_id], "refund policy")

    assert results[0].text == "our refund policy is thirty days"
    assert results[0].score_fts > 0


def test_another_companys_chunks_never_appear(db_conn, _fake_embeddings):
    company_a = _make_company(db_conn, "Company A")
    version_a = _make_version(db_conn, company_a)
    _make_chunk(db_conn, company_a, version_a, "company a secret pricing info", _vec(1.0))

    company_b = _make_company(db_conn, "Company B")
    version_b = _make_version(db_conn, company_b)
    _make_chunk(db_conn, company_b, version_b, "company a secret pricing info", _vec(1.0))  # same text, different tenant
    db_conn.commit()

    _fake_embeddings["vector"] = _vec(1.0)
    results = retrieve_with_version_ids(db_conn, company_a, [version_a], "pricing")

    assert len(results) == 1
    assert all(r.version_id == version_a for r in results)


def test_version_scoping_excludes_unauthorized_versions(db_conn, _fake_embeddings):
    company_id = _make_company(db_conn)
    authorized_version = _make_version(db_conn, company_id)
    unauthorized_version = _make_version(db_conn, company_id)
    _make_chunk(db_conn, company_id, authorized_version, "authorized content", _vec(1.0))
    _make_chunk(db_conn, company_id, unauthorized_version, "unauthorized content", _vec(1.0))
    db_conn.commit()

    _fake_embeddings["vector"] = _vec(1.0)
    results = retrieve_with_version_ids(db_conn, company_id, [authorized_version], "content")

    assert len(results) == 1
    assert results[0].text == "authorized content"


def test_language_filter_excludes_other_languages_when_given(db_conn, _fake_embeddings):
    company_id = _make_company(db_conn)
    version_id = _make_version(db_conn, company_id)
    _make_chunk(db_conn, company_id, version_id, "hours of operation are nine to five", _vec(1.0), language="en")
    _make_chunk(db_conn, company_id, version_id, "horario de atencion es de nueve a cinco", _vec(1.0), language="es")
    db_conn.commit()

    _fake_embeddings["vector"] = _vec(1.0)
    results = retrieve_with_version_ids(db_conn, company_id, [version_id], "hours", language_hint="en")

    assert len(results) == 1
    assert results[0].text.startswith("hours")


def test_language_filter_omitted_returns_all_languages(db_conn, _fake_embeddings):
    company_id = _make_company(db_conn)
    version_id = _make_version(db_conn, company_id)
    _make_chunk(db_conn, company_id, version_id, "english content here", _vec(1.0), language="en")
    _make_chunk(db_conn, company_id, version_id, "contenido en espanol aqui", _vec(1.0), language="es")
    db_conn.commit()

    _fake_embeddings["vector"] = _vec(1.0)
    results = retrieve_with_version_ids(db_conn, company_id, [version_id], "content", language_hint=None)

    assert len(results) == 2


def test_no_version_ids_returns_empty_without_a_query(db_conn, _fake_embeddings):
    company_id = _make_company(db_conn)
    assert retrieve_with_version_ids(db_conn, company_id, [], "anything") == []
