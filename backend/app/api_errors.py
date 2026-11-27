"""RFC 9457 problem-details error shape (ADR 007 "API conventions").

ADR 007: "Preserve the current shape for internal routes; add a `type`
URL for the public API only." The external developer API
(`/api/v1/public-api/*`, API keys + scopes) is Day 9 (D9.4) scope and
does not exist yet -- this module is the reusable helper Day 9's routes
will call, built now so that work is a wire-up, not a design decision.
It is not used anywhere yet and is inert until then.

Every other route (the existing authenticated owner API and the
visitor-facing `/api/v1/public/*` routes) keeps its current
`{"code", "message"}` detail shape unchanged -- do not route those
through this helper.
"""
from __future__ import annotations

TYPE_BASE_URL = "https://docs.knowmivo.com/errors"


def problem_detail(
    status: int,
    code: str,
    message: str,
    request_id: str | None = None,
    retry_after_seconds: int | None = None,
    fields: list[str] | None = None,
) -> dict:
    """Builds the RFC 9457 body: {type, title, status, code, message,
    request_id, retry_after_seconds?, fields?}. `type` is a stable,
    documented URL per error code -- never a bare slug -- so API key
    clients can link straight to the docs for a given failure."""
    body = {
        "type": f"{TYPE_BASE_URL}/{code}",
        "title": code.replace("_", " ").title(),
        "status": status,
        "code": code,
        "message": message,
        "request_id": request_id,
    }
    if retry_after_seconds is not None:
        body["retry_after_seconds"] = retry_after_seconds
    if fields:
        body["fields"] = fields
    return body
