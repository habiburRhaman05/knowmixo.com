"""Stripe billing endpoints (ADR 008, launch/09-BILLING-PAYMENTS.md).
Webhook ingestion, Checkout session creation, Customer Portal link,
plan sync, and entitlements.
"""
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth.service import SessionPrincipal
from app.billing.entitlements import entitlements, invalidate_entitlements
from app.config import settings
from app.db import connection
from app.deps import get_verified_principal

webhook_router = APIRouter(prefix="/api/v1/webhooks", tags=["billing"])
billing_router = APIRouter(prefix="/api/v1/billing", tags=["billing"])


@webhook_router.post("/stripe", status_code=200)
async def stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
):
    payload = await request.body()
    secret = settings().stripe_webhook_secret
    if not secret:
        raise HTTPException(
            status_code=503,
            detail={"code": "stripe_not_configured", "message": "Stripe webhook secret is not configured."},
        )
    if not stripe_signature:
        raise HTTPException(status_code=400, detail={"code": "missing_signature", "message": "Stripe-Signature header is required."})

    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, secret)
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_signature", "message": "Webhook signature verification failed."},
        ) from exc

    event_created = datetime.fromtimestamp(event["created"], tz=timezone.utc)
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO stripe_events (event_id, type, created_at, payload)
            VALUES (%s, %s, %s, %s::jsonb)
            ON CONFLICT (event_id) DO NOTHING
            """,
            (event["id"], event["type"], event_created, str(event)),
        )
    return {"received": True}


# --- Owner billing endpoints ------------------------------------------------


class CheckoutRequest(BaseModel):
    price_lookup_key: str = Field(..., max_length=100)


@billing_router.post("/checkout")
async def create_checkout_session(
    body: CheckoutRequest,
    request: Request,
    principal: SessionPrincipal = Depends(get_verified_principal),
):
    s = settings()
    if not s.stripe_secret_key:
        raise HTTPException(503, detail={"code": "stripe_not_configured", "message": "Stripe is not configured."})
    stripe.api_key = s.stripe_secret_key

    with connection() as conn:
        plan = conn.execute(
            "SELECT id FROM plans WHERE stripe_lookup_key = %s AND active = true",
            (body.price_lookup_key,),
        ).fetchone()
        if not plan:
            raise HTTPException(400, detail={"code": "invalid_plan", "message": "Plan not found."})

    prices = stripe.Price.list(lookup_keys=[body.price_lookup_key], active=True, limit=1)
    if not prices.data:
        raise HTTPException(400, detail={"code": "price_not_found", "message": "Stripe price not found for this plan."})

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": prices.data[0].id, "quantity": 1}],
        success_url=f"{s.public_app_url}/billing?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{s.public_app_url}/billing",
        metadata={"company_id": principal.company_id, "user_id": principal.user_id},
        automatic_tax={"enabled": s.stripe_tax_enabled},
        allow_promotion_codes=True,
    )
    return {"checkout_url": session.url}


@billing_router.post("/portal")
async def create_portal_session(
    principal: SessionPrincipal = Depends(get_verified_principal),
):
    s = settings()
    if not s.stripe_secret_key:
        raise HTTPException(503, detail={"code": "stripe_not_configured", "message": "Stripe is not configured."})
    stripe.api_key = s.stripe_secret_key

    with connection() as conn:
        sub = conn.execute(
            "SELECT stripe_customer_id FROM subscriptions WHERE company_id = %s AND stripe_customer_id IS NOT NULL LIMIT 1",
            (principal.company_id,),
        ).fetchone()
    if not sub or not sub["stripe_customer_id"]:
        raise HTTPException(400, detail={"code": "no_subscription", "message": "No active subscription found."})

    session = stripe.billing_portal.Session.create(
        customer=sub["stripe_customer_id"],
        return_url=f"{s.public_app_url}/billing",
    )
    return {"portal_url": session.url}


@billing_router.get("/plans")
async def list_plans():
    with connection() as conn:
        rows = conn.execute(
            "SELECT id, name, interval, limits, features, sort_order FROM plans WHERE active = true ORDER BY sort_order",
        ).fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "interval": r["interval"],
            "limits": r["limits"],
            "features": r["features"],
        }
        for r in rows
    ]


@billing_router.get("/me/plan")
async def my_plan(principal: SessionPrincipal = Depends(get_verified_principal)):
    ent = entitlements(principal.company_id)
    return ent


@billing_router.post("/me/plan/sync")
async def sync_plan(principal: SessionPrincipal = Depends(get_verified_principal)):
    invalidate_entitlements(principal.company_id)
    ent = entitlements(principal.company_id)
    return ent
