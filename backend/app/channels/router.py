"""Channel webhook endpoints (D6.1/D6.4): WhatsApp Cloud API + combined
Meta webhook for Messenger/Instagram. Each handler verifies the request,
resolves the external account to a bot via bot_channel_bindings, and
enqueues channel_inbound_message jobs -- processing happens on the jobs
runner, never inline, so Meta's fast-ack + aggressive-retry webhook
behavior never gets a slow response.
"""
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field

from app.auth.service import SessionPrincipal
from app.channels import bindings as bindings_service
from app.channels.bindings import resolve_binding
from app.channels.instagram import parse_inbound_webhook as parse_instagram
from app.channels.messenger import parse_inbound_webhook as parse_messenger
from app.channels.whatsapp import parse_inbound_webhook as parse_whatsapp
from app.channels.whatsapp import verify_webhook_signature, verify_webhook_token
from app.db import connection
from app.deps import get_verified_principal
from app.jobs.queue import enqueue_job

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/channels", tags=["channels"])


def _enqueue_inbound(company_id: str, bot_id: str, channel: str, external_id: str, text: str, message_id: str | None) -> None:
    with connection() as conn:
        enqueue_job(
            conn, company_id, kind="channel_inbound_message",
            payload={"company_id": company_id, "bot_id": bot_id, "channel": channel, "external_id": external_id, "text": text},
            idempotency_key=f"channel_inbound:{channel}:{message_id}" if message_id else None,
        )


# --- WhatsApp ---------------------------------------------------------------


@router.get("/whatsapp/webhook")
async def whatsapp_verify(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    result = verify_webhook_token(hub_mode, hub_verify_token, hub_challenge)
    if result is None:
        raise HTTPException(403, detail="verification_failed")
    return Response(content=result, media_type="text/plain")


@router.post("/whatsapp/webhook", status_code=200)
async def whatsapp_receive(request: Request, x_hub_signature_256: str | None = Header(default=None)):
    raw = await request.body()
    if not verify_webhook_signature(raw, x_hub_signature_256):
        raise HTTPException(401, detail="invalid_signature")

    payload = await request.json()
    parsed = parse_whatsapp(payload)

    for msg in parsed["messages"]:
        binding = resolve_binding("whatsapp", msg["phone_number_id"])
        if not binding:
            log.warning("no bot bound to WhatsApp phone_number_id %s", msg["phone_number_id"])
            continue
        _enqueue_inbound(
            binding["company_id"], binding["bot_id"], "whatsapp",
            msg["from"], msg["text"], msg["message_id"],
        )
    return {"received": True}


# --- Messenger + Instagram (combined Meta webhook) ---------------------------


@router.get("/meta/webhook")
async def meta_verify(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    result = verify_webhook_token(hub_mode, hub_verify_token, hub_challenge)
    if result is None:
        raise HTTPException(403, detail="verification_failed")
    return Response(content=result, media_type="text/plain")


@router.post("/meta/webhook", status_code=200)
async def meta_receive(request: Request, x_hub_signature_256: str | None = Header(default=None)):
    raw = await request.body()
    if not verify_webhook_signature(raw, x_hub_signature_256):
        raise HTTPException(401, detail="invalid_signature")

    payload = await request.json()
    object_type = payload.get("object")

    if object_type == "page":
        parsed = parse_messenger(payload)
        for msg in parsed["messages"]:
            binding = resolve_binding("messenger", msg["page_id"])
            if not binding:
                log.warning("no bot bound to Messenger page %s", msg["page_id"])
                continue
            _enqueue_inbound(
                binding["company_id"], binding["bot_id"], "messenger",
                msg["sender_id"], msg["text"], msg["message_id"],
            )
    elif object_type == "instagram":
        parsed = parse_instagram(payload)
        for msg in parsed["messages"]:
            binding = resolve_binding("instagram", msg["account_id"])
            if not binding:
                log.warning("no bot bound to Instagram account %s", msg["account_id"])
                continue
            _enqueue_inbound(
                binding["company_id"], binding["bot_id"], "instagram",
                msg["sender_id"], msg["text"], msg["message_id"],
            )
    else:
        log.warning("unknown Meta webhook object type %s", object_type)

    return {"received": True}


# --- Owner-facing binding CRUD -----------------------------------------------


class BindingCreate(BaseModel):
    bot_id: str
    channel: str = Field(..., pattern="^(whatsapp|messenger|instagram)$")
    external_account_id: str = Field(..., max_length=200)


@router.post("/bindings")
async def create_binding(body: BindingCreate, principal: SessionPrincipal = Depends(get_verified_principal)):
    return bindings_service.create_binding(principal.company_id, body.bot_id, body.channel, body.external_account_id)


@router.get("/bindings")
async def list_bindings(principal: SessionPrincipal = Depends(get_verified_principal)):
    return bindings_service.list_bindings(principal.company_id)


@router.delete("/bindings/{binding_id}")
async def delete_binding(binding_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    if not bindings_service.delete_binding(principal.company_id, binding_id):
        raise HTTPException(404, detail={"code": "binding_not_found", "message": "Binding not found."})
    return {"deleted": True}
