"""Webhook endpoints for Phase 7 - webhook management CRUD.

Endpoints for configuring HTTP webhook endpoints per company/bot.
Delivery is handled asynchronously via the job runner pattern.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, HttpUrl
from typing import Optional

from app.auth.service import SessionPrincipal
from app.db import connection
from app.deps import get_verified_principal

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


# --- Schemas ----------------------------------------------------------------


class WebhookEndpointCreate(BaseModel):
    url: HttpUrl
    events: list[str] = Field(default_factory=list)
    bot_id: Optional[str] = None  # optional: scope to specific bot


class WebhookEndpointUpdate(BaseModel):
    url: Optional[HttpUrl] = None
    events: Optional[list[str]] = None
    is_active: Optional[bool] = None


class WebhookEndpointResponse(BaseModel):
    id: str
    company_id: str
    bot_id: Optional[str]
    url: str
    events: list[str]
    is_active: bool
    created_at: str
    updated_at: str


class WebhookDeliveryResponse(BaseModel):
    id: str
    endpoint_id: str
    event_type: str
    status: str
    attempt: int
    max_attempts: int
    last_error: Optional[str]
    created_at: str
    delivered_at: Optional[str]


# --- Helpers ----------------------------------------------------------------


def _require_company(principal: SessionPrincipal) -> str:
    if not principal.company_id:
        raise HTTPException(status_code=404, detail={"code": "no_company", "message": "No company found."})
    return principal.company_id


# --- Endpoints --------------------------------------------------------------


@router.post("/endpoints", response_model=WebhookEndpointResponse, status_code=201)
def create_webhook_endpoint(
    body: WebhookEndpointCreate,
    principal: SessionPrincipal = Depends(get_verified_principal),
):
    """Create a new webhook endpoint for this company."""
    company_id = _require_company(principal)
    import secrets

    secret = secrets.token_urlsafe(32)

    try:
        with connection() as conn:
            bot_id = None
            if body.bot_id:
                # Verify bot belongs to this company
                bot = conn.execute(
                    "SELECT id FROM bots WHERE id = %s AND company_id = %s",
                    (body.bot_id, company_id),
                ).fetchone()
                if not bot:
                    raise HTTPException(status_code=404, detail={"code": "bot_not_found", "message": "Bot not found in this company."})
                bot_id = str(bot["id"])

            row = conn.execute(
                """
                INSERT INTO webhook_endpoints (company_id, bot_id, url, secret, events, is_active)
                VALUES (%s, %s, %s, %s, %s, true)
                RETURNING id, company_id, bot_id, url, events, is_active, created_at, updated_at
                """,
                (company_id, bot_id, str(body.url), secret, body.events),
            ).fetchone()

            return WebhookEndpointResponse(
                id=str(row["id"]),
                company_id=str(row["company_id"]),
                bot_id=str(row["bot_id"]) if row["bot_id"] else None,
                url=row["url"],
                events=row["events"],
                is_active=row["is_active"],
                created_at=row["created_at"].isoformat(),
                updated_at=row["updated_at"].isoformat(),
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "internal_error", "message": str(exc)})


@router.get("/endpoints", response_model=list[WebhookEndpointResponse])
def list_webhook_endpoints(
    principal: SessionPrincipal = Depends(get_verified_principal),
):
    """List all webhook endpoints for this company."""
    company_id = _require_company(principal)

    try:
        with connection() as conn:
            rows = conn.execute(
                """
                SELECT id, company_id, bot_id, url, events, is_active, created_at, updated_at
                FROM webhook_endpoints
                WHERE company_id = %s
                ORDER BY created_at DESC
                """,
                (company_id,),
            ).fetchall()

            return [
                WebhookEndpointResponse(
                    id=str(r["id"]),
                    company_id=str(r["company_id"]),
                    bot_id=str(r["bot_id"]) if r["bot_id"] else None,
                    url=r["url"],
                    events=r["events"],
                    is_active=r["is_active"],
                    created_at=r["created_at"].isoformat(),
                    updated_at=r["updated_at"].isoformat(),
                )
                for r in rows
            ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "internal_error", "message": str(exc)})


@router.get("/endpoints/{endpoint_id}", response_model=WebhookEndpointResponse)
def get_webhook_endpoint(
    endpoint_id: str,
    principal: SessionPrincipal = Depends(get_verified_principal),
):
    """Get a single webhook endpoint."""
    company_id = _require_company(principal)

    try:
        with connection() as conn:
            row = conn.execute(
                """
                SELECT id, company_id, bot_id, url, events, is_active, created_at, updated_at
                FROM webhook_endpoints
                WHERE id = %s AND company_id = %s
                """,
                (endpoint_id, company_id),
            ).fetchone()

            if not row:
                raise HTTPException(status_code=404, detail={"code": "endpoint_not_found", "message": "Webhook endpoint not found."})

            return WebhookEndpointResponse(
                id=str(row["id"]),
                company_id=str(row["company_id"]),
                bot_id=str(row["bot_id"]) if row["bot_id"] else None,
                url=row["url"],
                events=row["events"],
                is_active=row["is_active"],
                created_at=row["created_at"].isoformat(),
                updated_at=row["updated_at"].isoformat(),
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "internal_error", "message": str(exc)})


@router.patch("/endpoints/{endpoint_id}", response_model=WebhookEndpointResponse)
def update_webhook_endpoint(
    endpoint_id: str,
    body: WebhookEndpointUpdate,
    principal: SessionPrincipal = Depends(get_verified_principal),
):
    """Update a webhook endpoint."""
    company_id = _require_company(principal)

    try:
        with connection() as conn:
            # Verify ownership
            row = conn.execute(
                "SELECT id FROM webhook_endpoints WHERE id = %s AND company_id = %s",
                (endpoint_id, company_id),
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail={"code": "endpoint_not_found", "message": "Webhook endpoint not found."})

            # Build dynamic update
            updates = []
            params = []
            if body.url is not None:
                updates.append("url = %s")
                params.append(str(body.url))
            if body.events is not None:
                updates.append("events = %s")
                params.append(body.events)
            if body.is_active is not None:
                updates.append("is_active = %s")
                params.append(body.is_active)

            if not updates:
                raise HTTPException(status_code=400, detail={"code": "no_changes", "message": "No fields to update."})

            updates.append("updated_at = now()")
            params.extend([endpoint_id, company_id])

            row = conn.execute(
                f"""
                UPDATE webhook_endpoints
                SET {", ".join(updates)}
                WHERE id = %s AND company_id = %s
                RETURNING id, company_id, bot_id, url, events, is_active, created_at, updated_at
                """,
                tuple(params),
            ).fetchone()

            return WebhookEndpointResponse(
                id=str(row["id"]),
                company_id=str(row["company_id"]),
                bot_id=str(row["bot_id"]) if row["bot_id"] else None,
                url=row["url"],
                events=row["events"],
                is_active=row["is_active"],
                created_at=row["created_at"].isoformat(),
                updated_at=row["updated_at"].isoformat(),
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "internal_error", "message": str(exc)})


@router.delete("/endpoints/{endpoint_id}")
def delete_webhook_endpoint(
    endpoint_id: str,
    principal: SessionPrincipal = Depends(get_verified_principal),
):
    """Delete a webhook endpoint."""
    company_id = _require_company(principal)

    try:
        with connection() as conn:
            result = conn.execute(
                "DELETE FROM webhook_endpoints WHERE id = %s AND company_id = %s RETURNING id",
                (endpoint_id, company_id),
            ).fetchone()

            if not result:
                raise HTTPException(status_code=404, detail={"code": "endpoint_not_found", "message": "Webhook endpoint not found."})

            return {"status": "deleted", "endpoint_id": endpoint_id}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "internal_error", "message": str(exc)})


@router.get("/endpoints/{endpoint_id}/deliveries", response_model=list[WebhookDeliveryResponse])
def list_webhook_deliveries(
    endpoint_id: str,
    limit: int = 50,
    offset: int = 0,
    principal: SessionPrincipal = Depends(get_verified_principal),
):
    """List delivery attempts for a webhook endpoint."""
    company_id = _require_company(principal)

    try:
        with connection() as conn:
            # Verify ownership
            endpoint = conn.execute(
                "SELECT id FROM webhook_endpoints WHERE id = %s AND company_id = %s",
                (endpoint_id, company_id),
            ).fetchone()
            if not endpoint:
                raise HTTPException(status_code=404, detail={"code": "endpoint_not_found", "message": "Webhook endpoint not found."})

            rows = conn.execute(
                """
                SELECT id, endpoint_id, event_type, status, attempt, max_attempts,
                       last_error, created_at, delivered_at
                FROM webhook_deliveries
                WHERE endpoint_id = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (endpoint_id, limit, offset),
            ).fetchall()

            return [
                WebhookDeliveryResponse(
                    id=str(r["id"]),
                    endpoint_id=str(r["endpoint_id"]),
                    event_type=r["event_type"],
                    status=r["status"],
                    attempt=r["attempt"],
                    max_attempts=r["max_attempts"],
                    last_error=r["last_error"],
                    created_at=r["created_at"].isoformat(),
                    delivered_at=r["delivered_at"].isoformat() if r["delivered_at"] else None,
                )
                for r in rows
            ]
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail={"code": "internal_error", "message": str(exc)})