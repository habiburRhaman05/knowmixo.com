"""Escalation API (D5.3/D5.4/D6.1): rules CRUD, contacts CRUD + opt-in
verification, test-alert button, and the public deep-link resolver.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.auth.service import SessionPrincipal
from app.config import settings
from app.db import connection
from app.deps import get_verified_principal
from app.escalation import contacts as contacts_service
from app.escalation import rules as rules_service
from app.escalation import verification as verification_service
from app.escalation.deep_link import consume_jti, verify_jti_signature
from app.escalation.state_machine import acknowledge_escalation
from app.escalation.worker import test_alert as test_alert_service

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/escalations", tags=["escalations"])
public_router = APIRouter(tags=["escalations"])


# --- Rules --------------------------------------------------------------


class RuleCreate(BaseModel):
    name: str = Field(..., max_length=200)
    match: dict
    severity: str = Field(..., pattern="^(critical|high|medium|low)$")


class RuleUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    match: dict | None = None
    severity: str | None = Field(default=None, pattern="^(critical|high|medium|low)$")
    active: bool | None = None


@router.post("/rules")
async def create_rule(body: RuleCreate, principal: SessionPrincipal = Depends(get_verified_principal)):
    return rules_service.create_rule(principal.company_id, body.name, body.match, body.severity)


@router.get("/rules")
async def list_rules(principal: SessionPrincipal = Depends(get_verified_principal)):
    return rules_service.list_rules(principal.company_id)


@router.patch("/rules/{rule_id}")
async def update_rule(rule_id: str, body: RuleUpdate, principal: SessionPrincipal = Depends(get_verified_principal)):
    result = rules_service.update_rule(principal.company_id, rule_id, **body.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(404, detail={"code": "rule_not_found", "message": "Rule not found."})
    return result


@router.delete("/rules/{rule_id}")
async def delete_rule(rule_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    if not rules_service.delete_rule(principal.company_id, rule_id):
        raise HTTPException(404, detail={"code": "rule_not_found", "message": "Rule not found."})
    return {"deleted": True}


# --- Contacts + opt-in verification --------------------------------------


class ContactCreate(BaseModel):
    channel: str = Field(..., pattern="^(whatsapp|sms|email|slack|telegram|push)$")
    address: str = Field(..., max_length=500)
    priority: int = Field(..., ge=1)
    quiet_hours_tz: str | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None


class ContactUpdate(BaseModel):
    priority: int | None = Field(default=None, ge=1)
    active: bool | None = None
    quiet_hours_tz: str | None = None
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None


class VerifyCodeRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6)


@router.post("/contacts")
async def create_contact(body: ContactCreate, principal: SessionPrincipal = Depends(get_verified_principal)):
    return contacts_service.create_contact(
        principal.company_id, body.channel, body.address, body.priority,
        quiet_hours_tz=body.quiet_hours_tz, quiet_hours_start=body.quiet_hours_start, quiet_hours_end=body.quiet_hours_end,
    )


@router.get("/contacts")
async def list_contacts(principal: SessionPrincipal = Depends(get_verified_principal)):
    return contacts_service.list_contacts(principal.company_id)


@router.patch("/contacts/{contact_id}")
async def update_contact(contact_id: str, body: ContactUpdate, principal: SessionPrincipal = Depends(get_verified_principal)):
    result = contacts_service.update_contact(principal.company_id, contact_id, **body.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(404, detail={"code": "contact_not_found", "message": "Contact not found."})
    return result


@router.delete("/contacts/{contact_id}")
async def delete_contact(contact_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    if not contacts_service.delete_contact(principal.company_id, contact_id):
        raise HTTPException(404, detail={"code": "contact_not_found", "message": "Contact not found."})
    return {"deleted": True}


@router.post("/contacts/{contact_id}/send-code")
async def send_verification_code(contact_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    if not verification_service.send_verification_code(principal.company_id, contact_id):
        raise HTTPException(400, detail={"code": "send_failed", "message": "Could not send a verification code to this contact."})
    return {"sent": True}


@router.post("/contacts/{contact_id}/verify")
async def verify_contact(contact_id: str, body: VerifyCodeRequest, principal: SessionPrincipal = Depends(get_verified_principal)):
    if not verification_service.confirm_verification_code(principal.company_id, contact_id, body.code):
        raise HTTPException(400, detail={"code": "invalid_code", "message": "Invalid or expired verification code."})
    return {"verified": True}


# --- Test alert -----------------------------------------------------------


class TestAlertRequest(BaseModel):
    contact_id: str
    severity: str = Field(default="low", pattern="^(critical|high|medium|low)$")


@router.post("/test")
async def send_test_alert(body: TestAlertRequest, principal: SessionPrincipal = Depends(get_verified_principal)):
    result = test_alert_service(principal.company_id, body.contact_id, body.severity)
    if "error" in result:
        raise HTTPException(400, detail={"code": "test_alert_failed", "message": result["error"]})
    return result


# --- Public deep-link resolver ---------------------------------------------


@public_router.get("/t/{jti}")
async def resolve_deep_link(jti: str, request: Request):
    """launch/06-ESCALATION-DESIGN.md §4/§6: WhatsApp/Slack/Telegram
    acknowledge links. Single-use + 15-min expiry via Redis
    (escalation.deep_link.consume_jti); wrong HMAC signature -> 401,
    expired/already-used jti -> 410."""
    sig = request.query_params.get("sig")
    if not verify_jti_signature(jti, sig):
        raise HTTPException(401, detail={"code": "invalid_signature", "message": "Invalid link signature."})

    if not consume_jti(jti):
        raise HTTPException(410, detail={"code": "link_expired", "message": "This link has expired or was already used."})

    with connection() as conn:
        esc = conn.execute(
            "SELECT id, conversation_id FROM escalations WHERE deep_link_jti = %s", (jti,)
        ).fetchone()
    if not esc:
        raise HTTPException(410, detail={"code": "link_expired", "message": "This link is no longer valid."})

    acknowledge_escalation(str(esc["id"]), user_id=None, channel="link")

    base = settings().public_app_url
    if esc["conversation_id"]:
        return RedirectResponse(f"{base}/conversations/{esc['conversation_id']}?takeover=1")
    return RedirectResponse(f"{base}/escalations/{esc['id']}")
