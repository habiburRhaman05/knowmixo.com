from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth.service import SessionPrincipal
from app.db import connection
from app.deps import get_verified_principal
from app.sources import service
from app.sources.service import SourceError

router = APIRouter(prefix="/api/v1", tags=["sources"])


def _raise(exc: SourceError):
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
    try:
        with connection() as conn:
            result = service.start_file_upload(conn, company_id, body.filename, body.size_bytes)
    except SourceError as exc:
        _raise(exc)
    return result


@router.put("/uploads/{grant_id}", status_code=200)
async def upload_chunk(grant_id: str, request: Request):
    data = await request.body()
    try:
        total = service.write_upload_chunk(grant_id, data)
    except SourceError as exc:
        _raise(exc)
    return {"bytes_received": total}


class CompleteUploadRequest(BaseModel):
    grant_id: str


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
            job_id = service.complete_upload(conn, company_id, document_id, body.grant_id, idempotency_key)
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


@router.get("/documents")
def list_documents(principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    with connection() as conn:
        rows = service.list_documents(conn, company_id)
    return {"items": rows}


@router.get("/documents/{document_id}")
def get_document(document_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            row = service.get_document(conn, company_id, document_id)
    except SourceError as exc:
        _raise(exc)
    return row


@router.delete("/documents/{document_id}", status_code=202)
def delete_document(document_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            service.delete_document(conn, company_id, document_id)
    except SourceError as exc:
        _raise(exc)
    return {"status": "deleted"}


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry_job(job_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _require_company(principal)
    try:
        with connection() as conn:
            replayed = service.retry_job(conn, company_id, job_id)
    except SourceError as exc:
        _raise(exc)
    return {"replayed": replayed}
