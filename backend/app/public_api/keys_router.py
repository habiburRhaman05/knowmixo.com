"""Owner-facing API key management (D9.4, ADR 007). Under
/api/v1/api-keys -- distinct from /api/v1/public-api/* which is what
the keys themselves authenticate against.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.auth.service import SessionPrincipal
from app.deps import get_verified_principal
from app.public_api.keys import ALL_SCOPES, create_key, list_keys, revoke_key

router = APIRouter(prefix="/api/v1/api-keys", tags=["api-keys"])


class CreateKeyRequest(BaseModel):
    name: str = Field(default="API key", max_length=200)
    scopes: list[str] = Field(..., min_length=1)


@router.post("")
async def create_api_key(body: CreateKeyRequest, principal: SessionPrincipal = Depends(get_verified_principal)):
    try:
        return create_key(principal.company_id, principal.user_id, body.name, body.scopes)
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "invalid_scopes", "message": str(exc), "valid_scopes": sorted(ALL_SCOPES)})


@router.get("")
async def list_api_keys(principal: SessionPrincipal = Depends(get_verified_principal)):
    return list_keys(principal.company_id)


@router.delete("/{key_id}")
async def revoke_api_key(key_id: str, principal: SessionPrincipal = Depends(get_verified_principal)):
    if not revoke_key(principal.company_id, key_id):
        raise HTTPException(404, detail={"code": "key_not_found", "message": "API key not found or already revoked."})
    return {"revoked": True}
