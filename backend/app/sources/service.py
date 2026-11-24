"""Source creation/management business logic (docs/06-API.md "Uploads" /
"Other sources" / "Source management" sections, docs/16-API-ROUTES.md).
No FastAPI imports here -- app/sources/router.py is the thin HTTP adapter.
"""
import json
import uuid
from urllib.parse import urlparse

from app.bots.service import get_or_create_bot_for_company
from app.config import settings
from app.ingestion.crawler import CrawlError, discover_pages
from app.jobs.queue import enqueue_job
from app.security.ssrf_http import SSRFBlocked, validate_url as ssrf_validate_url
from app.storage import local as storage

MAX_PAGE_SIZE = 100


class SourceError(ValueError):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _require_uuid(value: str, code: str, message: str) -> None:
    try:
        uuid.UUID(value)
    except (ValueError, TypeError) as exc:
        raise SourceError(404, code, message) from exc


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


# --- Upload flow ------------------------------------------------------------


def start_file_upload(conn, company_id: str, filename: str, size_bytes: int) -> dict:
    bot_id = get_or_create_bot_for_company(conn, company_id)
    document_id, version_id, version = _create_document_and_version(conn, company_id, bot_id, "file", filename)

    try:
        grant = storage.create_upload_grant(company_id, document_id, version, filename, size_bytes)
    except storage.UploadError as exc:
        raise SourceError(422, exc.code, exc.message) from exc

    return {
        "document_id": document_id,
        "version_id": version_id,
        "grant_id": grant["grant_id"],
        "upload_url": f"/api/v1/uploads/{grant['grant_id']}",
        "expires_at": grant["expires_at"],
        "max_bytes": grant["max_bytes"],
    }


def write_upload_chunk(grant_id: str, data: bytes) -> int:
    try:
        return storage.write_upload_chunk(grant_id, data)
    except storage.UploadError as exc:
        raise SourceError(422, exc.code, exc.message) from exc


def complete_upload(conn, company_id: str, document_id: str, grant_id: str, idempotency_key: str | None, checksum: str | None = None) -> str:
    _require_uuid(document_id, "document_not_found", "Document not found.")
    document = conn.execute(
        "SELECT * FROM documents WHERE id = %s AND company_id = %s AND deleted_at IS NULL",
        (document_id, company_id),
    ).fetchone()
    if not document:
        raise SourceError(404, "document_not_found", "Document not found.")

    try:
        grant = storage._get_grant(grant_id)
        # The grant must have been issued for THIS company's THIS document.
        if grant["company_id"] != company_id or grant["document_id"] != document_id:
            raise SourceError(404, "grant_not_found", "This upload grant does not exist or was already used.")
        result = storage.finalize_upload(grant_id)
    except storage.UploadError as exc:
        raise SourceError(422, exc.code, exc.message) from exc
    if checksum and checksum.lower() != result["checksum"]:
        raise SourceError(422, "checksum_mismatch", "Uploaded file checksum does not match.")

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

    job_id, _is_new = enqueue_job(
        conn,
        company_id,
        kind="ingest_document",
        document_version_id=str(version["id"]),
        idempotency_key=idempotency_key or f"complete:{grant_id}",
    )
    return job_id


# --- Inline sources ---------------------------------------------------------


def create_text_source(conn, company_id: str, title: str, text: str) -> tuple[str, str]:
    bot_id = get_or_create_bot_for_company(conn, company_id)
    document_id, version_id, version = _create_document_and_version(conn, company_id, bot_id, "text", title)

    result = storage.write_text_content(company_id, document_id, version, text, suffix=".txt")
    conn.execute("UPDATE documents SET storage_key = %s WHERE id = %s", (result["storage_key"], document_id))
    conn.execute("UPDATE document_versions SET checksum = %s WHERE id = %s", (result["checksum"], version_id))

    job_id, _is_new = enqueue_job(conn, company_id, kind="ingest_document", document_version_id=version_id)
    return document_id, job_id


def create_faq_source(conn, company_id: str, title: str, items: list[dict]) -> tuple[str, str]:
    bot_id = get_or_create_bot_for_company(conn, company_id)
    document_id, version_id, version = _create_document_and_version(conn, company_id, bot_id, "faq", title)

    result = storage.write_text_content(company_id, document_id, version, json.dumps(items), suffix=".json")
    conn.execute("UPDATE documents SET storage_key = %s WHERE id = %s", (result["storage_key"], document_id))
    conn.execute("UPDATE document_versions SET checksum = %s WHERE id = %s", (result["checksum"], version_id))

    job_id, _is_new = enqueue_job(conn, company_id, kind="ingest_document", document_version_id=version_id)
    return document_id, job_id


def create_url_source(conn, company_id: str, url: str) -> tuple[str, str]:
    try:
        ssrf_validate_url(url)
    except SSRFBlocked as exc:
        raise SourceError(422, exc.code, exc.message) from exc

    bot_id = get_or_create_bot_for_company(conn, company_id)
    title = urlparse(url).netloc or url
    document_id, version_id, _version = _create_document_and_version(conn, company_id, bot_id, "url", title, source_url=url)

    job_id, _is_new = enqueue_job(conn, company_id, kind="ingest_document", document_version_id=version_id)
    return document_id, job_id


# --- Crawl ------------------------------------------------------------------


def create_crawl_source(conn, company_id: str, root_url: str) -> dict:
    """One-shot variant: discover and immediately ingest every page. The
    discover -> select -> import flow (start_crawl_discovery /
    import_crawl_pages) is the spec'd path; this is kept for simple
    "just import my site" callers."""
    try:
        pages = discover_pages(root_url, max_pages=settings().max_crawl_pages)
    except CrawlError as exc:
        raise SourceError(422, exc.code, exc.message) from exc

    if not pages:
        raise SourceError(422, "no_pages_discovered", "No pages were discovered at this URL.")

    bot_id = get_or_create_bot_for_company(conn, company_id)
    document_ids = []
    job_ids = []
    for page_url in pages:
        title = urlparse(page_url).path.strip("/") or urlparse(page_url).netloc
        document_id, version_id, _version = _create_document_and_version(
            conn, company_id, bot_id, "crawl_page", title, source_url=page_url
        )
        job_id, _is_new = enqueue_job(conn, company_id, kind="ingest_document", document_version_id=version_id)
        document_ids.append(document_id)
        job_ids.append(job_id)

    return {"document_ids": document_ids, "job_ids": job_ids, "pages_found": len(pages)}


def start_crawl_discovery(conn, company_id: str, root_url: str, max_pages: int | None) -> str:
    """POST /sources/crawl/discover: SSRF-validates the root URL up front,
    records a crawl_jobs row and queues a `crawl_discover` job."""
    try:
        ssrf_validate_url(root_url)
    except SSRFBlocked as exc:
        raise SourceError(422, exc.code, exc.message) from exc
    cap = settings().max_crawl_pages
    pages = max(1, min(max_pages or cap, cap))
    row = conn.execute(
        "INSERT INTO crawl_jobs (company_id, root_url, max_pages) VALUES (%s, %s, %s) RETURNING id",
        (company_id, root_url, pages),
    ).fetchone()
    crawl_job_id = str(row["id"])
    enqueue_job(
        conn,
        company_id,
        kind="crawl_discover",
        idempotency_key=f"crawl_discover:{crawl_job_id}",
        checkpoint_ref={"crawl_job_id": crawl_job_id},
    )
    return crawl_job_id


def get_crawl_job(conn, company_id: str, crawl_job_id: str) -> dict:
    _require_uuid(crawl_job_id, "crawl_job_not_found", "Crawl job not found.")
    row = conn.execute(
        "SELECT id, root_url, status, discovered_pages, error_code FROM crawl_jobs WHERE id = %s AND company_id = %s",
        (crawl_job_id, company_id),
    ).fetchone()
    if not row:
        raise SourceError(404, "crawl_job_not_found", "Crawl job not found.")
    return {
        "id": str(row["id"]),
        "root_url": row["root_url"],
        "status": row["status"],
        "discovered_pages": row["discovered_pages"],
        "error_code": row["error_code"],
    }


def import_crawl_pages(conn, company_id: str, crawl_job_id: str, selected_urls: list[str]) -> dict:
    """One source per SELECTED page. The selection must be a subset of what
    discovery found for this crawl job (never arbitrary URLs) and is capped
    at max_crawl_pages. Re-importing a page already imported is a no-op."""
    crawl = get_crawl_job(conn, company_id, crawl_job_id)
    if crawl["status"] != "completed":
        raise SourceError(409, "crawl_not_ready", "Crawl discovery has not completed.")
    found = {p["url"] for p in crawl["discovered_pages"]}
    selected = list(dict.fromkeys(selected_urls))
    if not selected:
        raise SourceError(422, "no_pages_selected", "Select at least one page to import.")
    if len(selected) > settings().max_crawl_pages:
        raise SourceError(422, "too_many_pages", f"Select at most {settings().max_crawl_pages} pages.")
    if any(u not in found for u in selected):
        raise SourceError(422, "page_not_discovered", "Selected pages must come from this crawl's discovered list.")

    bot_id = get_or_create_bot_for_company(conn, company_id)
    document_ids, job_ids = [], []
    for page_url in selected:
        existing = conn.execute(
            "SELECT 1 FROM documents WHERE company_id = %s AND kind = 'crawl_page' AND source_url = %s AND deleted_at IS NULL",
            (company_id, page_url),
        ).fetchone()
        if existing:
            continue
        title = urlparse(page_url).path.strip("/") or urlparse(page_url).netloc
        document_id, version_id, _v = _create_document_and_version(conn, company_id, bot_id, "crawl_page", title, source_url=page_url)
        job_id, _is_new = enqueue_job(conn, company_id, kind="ingest_document", document_version_id=version_id)
        document_ids.append(document_id)
        job_ids.append(job_id)
    return {"document_ids": document_ids, "job_ids": job_ids}


# --- Source management ------------------------------------------------------

# The LATEST version drives what the owner sees, so pending/failed sources
# are visible (documents.active_version_id is only set once a version is ready).
_LATEST_VERSION = """
    LEFT JOIN LATERAL (
        SELECT id, version, status, stage, error_code, chunk_count, ready_at
        FROM document_versions WHERE document_id = d.id ORDER BY version DESC LIMIT 1
    ) dv ON true
"""
_STATE_ALIASES = {"processing": ("pending", "processing", "retrying", "quota_wait")}


def _doc_row(r: dict) -> dict:
    return {
        "id": str(r["id"]),
        "type": r["kind"],
        "title": r["title"],
        "source_url": r["source_url"],
        "status": r["status"],
        "stage": r["stage"],
        "error_code": r["error_code"],
        "current_version": r["version"],
        "version_id": str(r["version_id"]) if r["version_id"] else None,
        "chunk_count": r["chunk_count"],
        "ready_at": r["ready_at"].isoformat() if r["ready_at"] else None,
        "created_at": r["created_at"].isoformat(),
    }


def list_documents(conn, company_id: str, state: str | None = None, kind: str | None = None, q: str | None = None,
                   cursor: str | None = None, limit: int = 25) -> dict:
    from app.bots.history import decode_cursor, encode_cursor

    limit = max(1, min(limit, MAX_PAGE_SIZE))
    where = ["d.company_id = %s", "d.deleted_at IS NULL"]
    params: list = [company_id]
    if state:
        where.append("dv.status = ANY(%s)")
        params.append(list(_STATE_ALIASES.get(state, (state,))))
    if kind:
        where.append("d.kind = %s")
        params.append(kind)
    if q:
        where.append("d.title ILIKE %s")
        params.append("%" + q.replace("%", "").replace("_", "") + "%")
    if cursor:
        ts, row_id = decode_cursor(cursor)
        where.append("(d.created_at, d.id) < (%s, %s::uuid)")
        params.extend([ts, row_id])

    rows = conn.execute(
        f"""
        SELECT d.id, d.kind, d.title, d.source_url, d.created_at,
               dv.id AS version_id, dv.version, dv.status, dv.stage, dv.error_code, dv.chunk_count, dv.ready_at
        FROM documents d {_LATEST_VERSION}
        WHERE {' AND '.join(where)}
        ORDER BY d.created_at DESC, d.id DESC LIMIT %s
        """,
        (*params, limit + 1),
    ).fetchall()
    page = rows[:limit]
    next_cursor = encode_cursor(page[-1]["created_at"], str(page[-1]["id"])) if len(rows) > limit else None
    return {"items": [_doc_row(r) for r in page], "next_cursor": next_cursor}


def get_document(conn, company_id: str, document_id: str) -> dict:
    _require_uuid(document_id, "document_not_found", "Document not found.")
    row = conn.execute(
        f"""
        SELECT d.id, d.kind, d.title, d.source_url, d.created_at,
               dv.id AS version_id, dv.version, dv.status, dv.stage, dv.error_code, dv.chunk_count, dv.ready_at
        FROM documents d {_LATEST_VERSION}
        WHERE d.id = %s AND d.company_id = %s AND d.deleted_at IS NULL
        """,
        (document_id, company_id),
    ).fetchone()
    if not row:
        raise SourceError(404, "document_not_found", "Document not found.")
    return _doc_row(row)


def rename_document(conn, company_id: str, document_id: str, title: str) -> None:
    _require_uuid(document_id, "document_not_found", "Document not found.")
    row = conn.execute(
        "UPDATE documents SET title = %s, updated_at = now() WHERE id = %s AND company_id = %s AND deleted_at IS NULL RETURNING id",
        (title, document_id, company_id),
    ).fetchone()
    if not row:
        raise SourceError(404, "document_not_found", "Document not found.")


def get_document_content(conn, company_id: str, document_id: str, max_chars: int = 20000) -> dict:
    """Extracted-text preview of the ACTIVE (ready) version, never raw file
    passthrough (docs/16)."""
    _require_uuid(document_id, "document_not_found", "Document not found.")
    doc = conn.execute(
        "SELECT id, title, active_version_id FROM documents WHERE id = %s AND company_id = %s AND deleted_at IS NULL",
        (document_id, company_id),
    ).fetchone()
    if not doc:
        raise SourceError(404, "document_not_found", "Document not found.")
    if not doc["active_version_id"]:
        raise SourceError(409, "content_not_ready", "No ready version of this source exists yet.")
    chunks = conn.execute(
        "SELECT ordinal, page, heading, text FROM chunks WHERE version_id = %s ORDER BY ordinal ASC",
        (doc["active_version_id"],),
    ).fetchall()

    preview, used, truncated = [], 0, False
    for c in chunks:
        text = c["text"] or ""
        if used + len(text) > max_chars:
            preview.append(text[: max(0, max_chars - used)])
            truncated = True
            break
        preview.append(text)
        used += len(text)

    outline, seen = [], set()
    for c in chunks:
        key = (c["page"], c["heading"])
        if key in seen or (c["page"] is None and not c["heading"]):
            continue
        seen.add(key)
        outline.append({"page": c["page"], "heading": c["heading"]})
    return {"title": doc["title"], "preview_text": "\n\n".join(preview), "truncated": truncated, "pages_or_headings": outline}


def delete_document(conn, company_id: str, document_id: str) -> None:
    """Revokes access immediately (deleted_at set in this same transaction,
    excluding it from list/get, owner preview and visitor retrieval, which
    all re-check deleted_at in Postgres). Physical vector cleanup is
    best-effort and never blocks or fails the deletion response."""
    _require_uuid(document_id, "document_not_found", "Document not found.")
    row = conn.execute(
        "UPDATE documents SET deleted_at = now(), updated_at = now() WHERE id = %s AND company_id = %s AND deleted_at IS NULL RETURNING id",
        (document_id, company_id),
    ).fetchone()
    if not row:
        raise SourceError(404, "document_not_found", "Document not found.")

    versions = conn.execute("SELECT id FROM document_versions WHERE document_id = %s", (document_id,)).fetchall()
    try:
        from app.providers.vector_store import delete_version_vectors

        for v in versions:
            delete_version_vectors(company_id, str(v["id"]))
    except Exception:  # noqa: BLE001 -- deletion already recorded above; retention sweep reconciles leftovers
        pass


_NON_TERMINAL_VERSION_STATUSES = ("pending", "processing", "retrying", "quota_wait")


def refresh_document(conn, company_id: str, document_id: str) -> str:
    """Creates a new version of the same content and reprocesses it. The old
    version stays active until the new one is ready. Blocked while a version
    is mid-processing (two versions racing over one storage_key)."""
    _require_uuid(document_id, "document_not_found", "Document not found.")
    document = conn.execute(
        "SELECT id FROM documents WHERE id = %s AND company_id = %s AND deleted_at IS NULL",
        (document_id, company_id),
    ).fetchone()
    if not document:
        raise SourceError(404, "document_not_found", "Document not found.")

    latest = conn.execute(
        "SELECT id, version, status FROM document_versions WHERE document_id = %s ORDER BY version DESC LIMIT 1",
        (document_id,),
    ).fetchone()
    if latest and latest["status"] in _NON_TERMINAL_VERSION_STATUSES:
        raise SourceError(409, "refresh_in_progress", "A version is already being processed for this source.")

    next_version = (latest["version"] if latest else 0) + 1
    version_row = conn.execute(
        "INSERT INTO document_versions (document_id, version) VALUES (%s, %s) RETURNING id",
        (document_id, next_version),
    ).fetchone()

    job_id, _is_new = enqueue_job(conn, company_id, kind="ingest_document", document_version_id=str(version_row["id"]))
    return job_id


# --- Jobs -------------------------------------------------------------------


def get_job(conn, company_id: str, job_id: str) -> dict:
    _require_uuid(job_id, "job_not_found", "Job not found.")
    row = conn.execute(
        "SELECT id, kind, state, stage, attempts, max_attempts, error_code, available_at FROM jobs WHERE id = %s AND company_id = %s",
        (job_id, company_id),
    ).fetchone()
    if not row:
        raise SourceError(404, "job_not_found", "Job not found.")
    return {
        "id": str(row["id"]),
        "kind": row["kind"],
        "state": row["state"],
        "stage": row["stage"],
        "attempts": row["attempts"],
        "max_attempts": row["max_attempts"],
        "error_code": row["error_code"],
        "available_at": row["available_at"].isoformat() if row["available_at"] else None,
    }


def retry_job(conn, company_id: str, job_id: str) -> dict:
    """Safe replay: only a 'dead' job is requeued, and the document version
    it targets must still be current (a deleted source or superseded version
    is never resurrected). A second call is a no-op."""
    _require_uuid(job_id, "job_not_found", "Job not found.")
    job = conn.execute(
        "SELECT id, document_version_id FROM jobs WHERE id = %s AND company_id = %s", (job_id, company_id)
    ).fetchone()
    if not job:
        raise SourceError(404, "job_not_found", "Job not found.")

    if job["document_version_id"]:
        current = conn.execute(
            """
            SELECT dv.version = (SELECT MAX(version) FROM document_versions WHERE document_id = d.id) AS is_latest
            FROM document_versions dv JOIN documents d ON d.id = dv.document_id
            WHERE dv.id = %s AND d.deleted_at IS NULL
            """,
            (job["document_version_id"],),
        ).fetchone()
        if not current:
            raise SourceError(409, "source_deleted", "The source for this job was deleted.")
        if not current["is_latest"]:
            raise SourceError(409, "source_version_superseded", "A newer version of this source exists.")

    from app.jobs.runner import replay_dead_job

    replayed = replay_dead_job(conn, job_id)
    attempts = conn.execute("SELECT attempts FROM jobs WHERE id = %s", (job_id,)).fetchone()["attempts"]
    return {"replayed": replayed, "new_attempt_generation": attempts + 1 if replayed else attempts}
