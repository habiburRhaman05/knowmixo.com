"""Analytics API (D8.2): /analytics/series?metric=conversations|deflection|ttft."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.analytics import service
from app.auth.service import SessionPrincipal
from app.db import connection
from app.deps import get_verified_principal

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])


@router.get("/series")
async def get_series(
    metric: str = Query(..., pattern="^(conversations|deflection|ttft)$"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    principal: SessionPrincipal = Depends(get_verified_principal),
):
    with connection() as conn:
        try:
            data = service.get_series(conn, principal.company_id, metric, date_from, date_to)
        except ValueError as exc:
            raise HTTPException(422, detail={"code": "invalid_metric", "message": str(exc)})
    return {"metric": metric, "series": data}
