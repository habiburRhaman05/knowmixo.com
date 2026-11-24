"""Owner dashboard + usage (docs/16-API-ROUTES.md "Dashboard / usage").

No paid-upgrade fields: quota exhaustion is reported as state + reset time
only (docs/16: "No paid-upgrade fields")."""
from fastapi import APIRouter, Depends, HTTPException

from app.auth.service import SessionPrincipal
from app.chat import quota
from app.db import connection
from app.deps import get_verified_principal

router = APIRouter(prefix="/api/v1", tags=["dashboard"])


def _company(principal: SessionPrincipal) -> str:
    if not principal.company_id:
        raise HTTPException(status_code=404, detail={"code": "no_company", "message": "No company found."})
    return principal.company_id


@router.get("/dashboard")
def get_dashboard(principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _company(principal)
    with connection() as conn:
        counts = conn.execute(
            """
            SELECT dv.status, COUNT(*) AS n
            FROM documents d
            JOIN LATERAL (SELECT status FROM document_versions WHERE document_id = d.id ORDER BY version DESC LIMIT 1) dv ON true
            WHERE d.company_id = %s AND d.deleted_at IS NULL
            GROUP BY dv.status
            """,
            (company_id,),
        ).fetchall()
        source_counts = {r["status"]: int(r["n"]) for r in counts}

        bot = conn.execute(
            "SELECT id, draft_config, active_publication_id FROM bots WHERE company_id = %s", (company_id,)
        ).fetchone()
        conversation_count = 0
        if bot:
            conversation_count = conn.execute(
                "SELECT COUNT(*) AS n FROM conversations WHERE bot_id = %s AND NOT is_preview", (bot["id"],)
            ).fetchone()["n"]
        snapshot = quota.usage_snapshot(conn, company_id)

    ready = source_counts.get("ready", 0)
    config = (bot["draft_config"] if bot else None) or {}
    checklist = [
        {"key": "add_source", "label": "Add a knowledge source", "done": sum(source_counts.values()) > 0},
        {"key": "source_ready", "label": "Have at least one ready source", "done": ready > 0},
        {"key": "configure_bot", "label": "Configure your assistant", "done": bool(config.get("name"))},
        {"key": "publish", "label": "Publish your assistant", "done": bool(bot and bot["active_publication_id"])},
    ]
    summary = quota.public_usage(snapshot)
    return {
        "setup_checklist": checklist,
        "source_counts_by_state": source_counts,
        "conversation_count": int(conversation_count),
        "usage_summary": {
            "requests_today": summary["company_daily"]["requests"],
            "limit": summary["company_daily"]["limit"],
            "quota_state": summary["quota_state"],
        },
    }


@router.get("/usage")
def get_usage(principal: SessionPrincipal = Depends(get_verified_principal)):
    company_id = _company(principal)
    with connection() as conn:
        snapshot = quota.usage_snapshot(conn, company_id)
    return quota.public_usage(snapshot)
