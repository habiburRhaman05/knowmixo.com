"""RFC 9457 problem-details error shape for the public API only (ADR 007:
"Preserve the current shape for internal routes; add `type` URL for the
public API only"). {type, title, status, code, message, request_id,
retry_after_seconds?, fields?}.
"""
from fastapi import Request
from fastapi.responses import JSONResponse

PROBLEM_TYPE_BASE = "https://docs.knowmivo.com/errors"


class PublicAPIError(Exception):
    def __init__(self, status_code: int, code: str, message: str, retry_after_seconds: int | None = None, fields: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.retry_after_seconds = retry_after_seconds
        self.fields = fields


def problem_response(request: Request, exc: PublicAPIError) -> JSONResponse:
    body = {
        "type": f"{PROBLEM_TYPE_BASE}/{exc.code}",
        "title": exc.code.replace("_", " ").title(),
        "status": exc.status_code,
        "code": exc.code,
        "message": exc.message,
        "request_id": getattr(request.state, "request_id", None),
    }
    if exc.retry_after_seconds:
        body["retry_after_seconds"] = exc.retry_after_seconds
    if exc.fields:
        body["fields"] = exc.fields
    headers = {"Retry-After": str(exc.retry_after_seconds)} if exc.retry_after_seconds else None
    return JSONResponse(status_code=exc.status_code, content=body, media_type="application/problem+json", headers=headers)
