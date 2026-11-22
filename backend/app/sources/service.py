"""Source creation/management business logic (docs/06-API.md "Uploads" /
"Other sources" / "Source management" sections). No FastAPI imports here
-- app/sources/router.py is the thin HTTP adapter.
"""
from urllib.parse import urlparse

from app.bots.service import get_or_create_bot_for_company
from app.jobs.queue import enqueue_job
from app.security.ssrf_http import SSRFBlocked, validate_url as ssrf_validate_url
from app.storage import local as storage


class SourceError(ValueError):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _create_document_and_version(conn, company_id: str, bot_id: str, kind: str, title: str, source_url: str | None = None) -> tuple[str, str, int]:
    document = conn.execute(
        """
        INSERT INTO documents (company_id, bot_id, kind, title, source_url)
        VALUES (%s, %s, %s, %s, %s)
        RETURNING id
        """,
        (company_id, bot_id, kind, title, source_url),
    ).fetchone()
    document_id = str(document["id"])

    version_row = conn.execute(
        "INSERT INTO document_versions (document_id, version) VALUES (%s, 1) RETURNING id",
        (document_id,),
    ).fetchone()
    version_id = str(version_row["id"])

    return document_id, version_id, 1


def start_file_upload(conn, company_id: str, filename: str, size_bytes: int) -> dict:
    bot_id = get_or_create_bot_for_company(conn, company_id)
    document_id, version_id, version = _create_document_and_version(conn, company_id, bot_id, "file", filename)

    try:
        grant = storage.create_upload_grant(company_id, document_id, version, filename, size_bytes)
    except storage.UploadError as exc:
        raise SourceError(422, exc.code, exc.message) from exc

    return {"document_id": document_id, "version_id": version_id, **grant}


def write_upload_chunk(grant_id: str, data: bytes) -> int:
    try:
        return storage.write_upload_chunk(grant_id, data)
    except storage.UploadError as exc:
        raise SourceError(422, exc.code, exc.message) from exc


def complete_upload(conn, company_id: str, document_id: str, grant_id: str, idempotency_key: str | None) -> str:
    document = conn.execute(
        "SELECT * FROM documents WHERE id = %s AND company_id = %s AND deleted_at IS NULL",
        (document_id, company_id),
    ).fetchone()
    if not document:
        raise SourceError(404, "document_not_found", "Document not found.")

    try:
        result = storage.finalize_upload(grant_id)
    except storage.UploadError as exc:
        raise SourceError(422, exc.code, exc.message) from exc

    version = conn.execute(
        "SELECT id FROM document_versions WHERE document_id = %s ORDER BY version DESC LIMIT 1",
        (document_id,),
    ).fetchone()

    conn.execute(
        "UPDATE documents SET storage_key = %s, updated_at = now() WHERE id = %s",
        (result["storage_key"], document_id),
    )
    conn.execute(
        "UPDATE document_versions SET checksum = %s WHERE id = %s",
        (result["checksum"], version["id"]),
    )

    job_id = enqueue_job(
        conn,
        company_id,
        kind="ingest_document",
        document_version_id=str(version["id"]),
        idempotency_key=idempotency_key or f"complete:{grant_id}",
    )
    return job_id


def create_text_source(conn, company_id: str, title: str, text: str) -> tuple[str, str]:
    bot_id = get_or_create_bot_for_company(conn, company_id)
    document_id, version_id, version = _create_document_and_version(conn, company_id, bot_id, "text", title)

    result = storage.write_text_content(company_id, document_id, version, text, suffix=".txt")
    conn.execute("UPDATE documents SET storage_key = %s WHERE id = %s", (result["storage_key"], document_id))
    conn.execute("UPDATE document_versions SET checksum = %s WHERE id = %s", (result["checksum"], version_id))

    job_id = enqueue_job(conn, company_id, kind="ingest_document", document_version_id=version_id)
    return document_id, job_id


def create_faq_source(conn, company_id: str, title: str, items: list[dict]) -> tuple[str, str]:
    import json

    bot_id = get_or_create_bot_for_company(conn, company_id)
    document_id, version_id, version = _create_document_and_version(conn, company_id, bot_id, "faq", title)

    result = storage.write_text_content(company_id, document_id, version, json.dumps(items), suffix=".json")
    conn.execute("UPDATE documents SET storage_key = %s WHERE id = %s", (result["storage_key"], document_id))
    conn.execute("UPDATE document_versions SET checksum = %s WHERE id = %s", (result["checksum"], version_id))

    job_id = enqueue_job(conn, company_id, kind="ingest_document", document_version_id=version_id)
    return document_id, job_id


def create_url_source(conn, company_id: str, url: str) -> tuple[str, str]:
    try:
        ssrf_validate_url(url)
    except SSRFBlocked as exc:
        raise SourceError(422, exc.code, exc.message) from exc

    bot_id = get_or_create_bot_for_company(conn, company_id)
    title = urlparse(url).netloc or url
    document_id, version_id, _version = _create_document_and_version(conn, company_id, bot_id, "url", title, source_url=url)

    job_id = enqueue_job(conn, company_id, kind="ingest_document", document_version_id=version_id)
    return document_id, job_id


def list_documents(conn, company_id: str) -> list[dict]:
    return conn.execute(
        """
        SELECT d.id, d.kind, d.title, d.source_url, d.created_at,
               dv.status, dv.stage, dv.error_code, dv.chunk_count, dv.ready_at
        FROM documents d
        LEFT JOIN document_versions dv ON dv.id = d.active_version_id
        WHERE d.company_id = %s AND d.deleted_at IS NULL
        ORDER BY d.created_at DESC
        LIMIT 100
        """,
        (company_id,),
    ).fetchall()


def get_document(conn, company_id: str, document_id: str) -> dict:
    row = conn.execute(
        """
        SELECT d.*, dv.status, dv.stage, dv.error_code, dv.chunk_count, dv.ready_at
        FROM documents d
        LEFT JOIN document_versions dv ON dv.id = d.active_version_id
        WHERE d.id = %s AND d.company_id = %s AND d.deleted_at IS NULL
        """,
        (document_id, company_id),
    ).fetchone()
    if not row:
        raise SourceError(404, "document_not_found", "Document not found.")
    return row


def delete_document(conn, company_id: str, document_id: str) -> None:
    """Revokes access immediately (deleted_at set in this same
    transaction, excluding it from list_documents/get_document and any
    future chat retrieval). Physical vector cleanup is attempted
    best-effort and does not block or fail the deletion response --
    full durable delete-cleanup-as-a-job lands with Phase 7's lifecycle
    work (docs/19-BACKEND-SPRINT-PLAN-V2.md)."""
    row = conn.execute(
        "UPDATE documents SET deleted_at = now(), updated_at = now() WHERE id = %s AND company_id = %s AND deleted_at IS NULL RETURNING active_version_id",
        (document_id, company_id),
    ).fetchone()
    if not row:
        raise SourceError(404, "document_not_found", "Document not found.")

    if row["active_version_id"]:
        try:
            from app.providers.vector_store import delete_version_vectors

            delete_version_vectors(company_id, str(row["active_version_id"]))
        except Exception:  # noqa: BLE001 -- best-effort; deletion already committed above
            pass


def retry_job(conn, company_id: str, job_id: str) -> bool:
    job = conn.execute("SELECT id FROM jobs WHERE id = %s AND company_id = %s", (job_id, company_id)).fetchone()
    if not job:
        raise SourceError(404, "job_not_found", "Job not found.")

    from app.jobs.runner import replay_dead_job

    return replay_dead_job(conn, job_id)
