"""Slack integration API (D9.5): OAuth install flow + status."""
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.auth.service import SessionPrincipal
from app.config import settings
from app.deps import get_verified_principal
from app.integrations import slack

router = APIRouter(prefix="/api/v1/integrations/slack", tags=["integrations"])
public_router = APIRouter(prefix="/api/v1/integrations/slack", tags=["integrations"])


@router.get("/install")
async def install(principal: SessionPrincipal = Depends(get_verified_principal)):
    try:
        url = slack.install_url(principal.company_id)
    except slack.SlackError as exc:
        raise HTTPException(exc.status_code, detail={"code": exc.code, "message": exc.message})
    return {"install_url": url}


@public_router.get("/callback")
async def callback(code: str | None = Query(default=None), state: str | None = Query(default=None), error: str | None = Query(default=None)):
    base = settings().public_app_url
    if error or not code or not state:
        return RedirectResponse(f"{base}/integrations?slack=error")
    try:
        slack.complete_install(code, state, installed_by=None)
    except slack.SlackError:
        return RedirectResponse(f"{base}/integrations?slack=error")
    return RedirectResponse(f"{base}/integrations?slack=connected")


@router.get("/status")
async def status(principal: SessionPrincipal = Depends(get_verified_principal)):
    installation = slack.get_installation(principal.company_id)
    return {"connected": installation is not None, **(installation or {})}


@router.delete("")
async def uninstall(principal: SessionPrincipal = Depends(get_verified_principal)):
    slack.uninstall(principal.company_id)
    return {"disconnected": True}
