from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from app.auth.service import SessionPrincipal
from app.bots.service import BotError
from app.db import connection
from app.deps import get_verified_principal
from app.idempotency import run_idempotent
from app.sources import service
from app.sources.service import SourceError

router = APIRouter(prefix="/api/v1", tags=["sources"])

ALLOWED_UPLOAD_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/vnd.ms-excel",  # some browsers send this for .csv
    "application/octet-stream",  # browsers often send this; the magic-byte check is authoritative
}


def _raise(exc: SourceError | BotError):
    raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def _require_company(principal: SessionPrincipal) -> str:
    if not principal.company_id:
        raise HTTPException(status_code=404, detail={"code": "no_company", "message": "No company found."})
    return principal.company_id


class UploadGrantRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str
    size_bytes: int = Field(gt=0)


@router.post("/documents/uploads", status_code=201)
def create_upload(body: UploadGrantRequest, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    if body.content_type.split(";")[0].strip().lower() not in ALLOWED_UPLOAD_CONTENT_TYPES:
        raise HTTPException(status_code=422, detail={"code": "unsupported_file_type", "message": "Allowed types: PDF, DOCX, TXT, MD, CSV."})
    try:
        with connection() as conn:
            result = service.start_file_upload(conn, company_id, body.filename, body.size_bytes)
    except SourceError as exc:
        _raise(exc)
    return result


@router.put("/uploads/{grant_id}", status_code=200)
async def upload_chunk(grant_id: str, request: Request):
    """Authorised by the unguessable, short-lived, size-capped grant token
    itself (docs/16: 'grant token')."""
    data = await request.body()
    try:
        total = service.write_upload_chunk(grant_id, data)
    except SourceError as exc:
        _raise(exc)
    return {"bytes_received": total}


class CompleteUploadRequest(BaseModel):
    grant_id: str
    checksum: str | None = Field(default=None, min_length=64, max_length=64)


@router.post("/documents/{document_id}/complete", status_code=202)
def complete_upload(
    document_id: str,
    body: CompleteUploadRequest,
    principal: SessionPrincipal = Depends(get_verified_principal),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            job_id = service.complete_upload(conn, company_id, document_id, body.grant_id, idempotency_key, body.checksum)
    except SourceError as exc:
        _raise(exc)
    return {"job_id": job_id}


class TextSourceRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=1_000_000)


@router.post("/sources/text", status_code=202)
def create_text_source(body: TextSourceRequest, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    with connection() as conn:
        document_id, job_id = service.create_text_source(conn, company_id, body.title, body.text)
    return {"document_id": document_id, "job_id": job_id}


class FAQItem(BaseModel):
    q: str = Field(min_length=1, max_length=500)
    a: str = Field(min_length=1, max_length=5000)


class FAQSourceRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    items: list[FAQItem] = Field(min_length=1, max_length=200)


@router.post("/sources/faqs", status_code=202)
def create_faq_source(body: FAQSourceRequest, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    with connection() as conn:
        document_id, job_id = service.create_faq_source(
            conn, company_id, body.title, [item.model_dump() for item in body.items]
        )
    return {"document_id": document_id, "job_id": job_id}


class URLSourceRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


@router.post("/sources/url", status_code=202)
def create_url_source(body: URLSourceRequest, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            document_id, job_id = service.create_url_source(conn, company_id, body.url)
    except SourceError as exc:
        _raise(exc)
    return {"document_id": document_id, "job_id": job_id}


# --- Crawl ------------------------------------------------------------------


class CrawlSourceRequest(BaseModel):
    root_url: str = Field(min_length=1, max_length=2000)


@router.post("/sources/crawl", status_code=202)
def create_crawl_source(body: CrawlSourceRequest, principal: SessionPrincipal = Depends(get_verified_principal)):
    """One-shot: discover same-domain pages and ingest all of them."""
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            result = service.create_crawl_source(conn, company_id, body.root_url)
    except SourceError as exc:
        _raise(exc)
    return result


class CrawlDiscoverRequest(BaseModel):
    root_url: str = Field(min_length=1, max_length=2000)
    max_pages: int | None = Field(default=None, ge=1, le=200)


@router.post("/sources/crawl/discover", status_code=202)
def discover_crawl(body: CrawlDiscoverRequest, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            crawl_job_id = service.start_crawl_discovery(conn, company_id, body.root_url, body.max_pages)
    except SourceError as exc:
        _raise(exc)
    return {"crawl_job_id": crawl_job_id}


@router.get("/crawl-jobs/{crawl_job_id}")
def get_crawl_job(crawl_job_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            job = service.get_crawl_job(conn, company_id, crawl_job_id)
    except SourceError as exc:
        _raise(exc)
    return {"status": job["status"], "discovered_pages": job["discovered_pages"], "error_code": job["error_code"]}


class CrawlImportRequest(BaseModel):
    selected_urls: list[str] = Field(min_length=1, max_length=200)


@router.post("/crawl-jobs/{crawl_job_id}/import", status_code=202)
def import_crawl(
    crawl_job_id: str,
    body: CrawlImportRequest,
    response: Response,
    principal: SessionPrincipal = Depends(get_verified_principal),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            result, replayed = run_idempotent(
                conn, company_id, f"crawl.import:{crawl_job_id}", idempotency_key, sorted(body.selected_urls),
                lambda: service.import_crawl_pages(conn, company_id, crawl_job_id, body.selected_urls), 202,
            )
    except (SourceError, BotError) as exc:
        _raise(exc)
    if replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return result


# --- Source management ------------------------------------------------------


@router.get("/documents")
def list_documents(
    state: str | None = None,
    type: str | None = Query(default=None, alias="type"),
    q: str | None = Query(default=None, max_length=200),
    cursor: str | None = None,
    limit: int = Query(default=25, ge=1, le=service.MAX_PAGE_SIZE),
    principal: SessionPrincipal = Depends(get_verified_principal),
):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            return service.list_documents(conn, company_id, state, type, q, cursor, limit)
    except BotError as exc:
        _raise(exc)


@router.get("/documents/{document_id}")
def get_document(document_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            row = service.get_document(conn, company_id, document_id)
    except SourceError as exc:
        _raise(exc)
    return row


class DocumentPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)


@router.patch("/documents/{document_id}")
def patch_document(document_id: str, body: DocumentPatch, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            if body.title is not None:
                service.rename_document(conn, company_id, document_id, body.title)
            row = service.get_document(conn, company_id, document_id)
    except SourceError as exc:
        _raise(exc)
    return row


@router.get("/documents/{document_id}/content")
def get_document_content(document_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            return service.get_document_content(conn, company_id, document_id)
    except SourceError as exc:
        _raise(exc)


@router.post("/documents/{document_id}/refresh", status_code=202)
def refresh_document(
    document_id: str,
    response: Response,
    principal: SessionPrincipal = Depends(get_verified_principal),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            result, replayed = run_idempotent(
                conn, company_id, f"document.refresh:{document_id}", idempotency_key, {},
                lambda: {"job_id": service.refresh_document(conn, company_id, document_id)}, 202,
            )
    except (SourceError, BotError) as exc:
        _raise(exc)
    if replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return result


@router.delete("/documents/{document_id}", status_code=202)
def delete_document(document_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            service.delete_document(conn, company_id, document_id)
    except SourceError as exc:
        _raise(exc)
    return {"status": "deleted"}


# --- Jobs -------------------------------------------------------------------


@router.get("/jobs/{job_id}")
def get_job(job_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            return service.get_job(conn, company_id, job_id)
    except SourceError as exc:
        _raise(exc)


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry_job(
    job_id: str,
    response: Response,
    principal: SessionPrincipal = Depends(get_verified_principal),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            result, replayed = run_idempotent(
                conn, company_id, f"job.retry:{job_id}", idempotency_key, {},
                lambda: service.retry_job(conn, company_id, job_id), 202,
            )
    except (SourceError, BotError) as exc:
        _raise(exc)
    if replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return result
