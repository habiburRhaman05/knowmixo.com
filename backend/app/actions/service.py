"""HTTP actions CRUD and execution (D5.2).
Uses app.security.ssrf_http for SSRF-safe outbound fetches.
"""
import json
import logging

import httpx

from app.db import connection
from app.security.ssrf_http import SSRFBlocked, validate_url

log = logging.getLogger(__name__)


def create_action(company_id: str, bot_id: str, *, name: str, url: str, method: str = "POST",
                  headers: dict | None = None, body_template: dict | None = None,
                  description: str = "", timeout_ms: int = 5000) -> dict:
    validate_url(url)
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO http_actions (company_id, bot_id, name, description, method, url, headers, body_template, timeout_ms)
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
            RETURNING id, name, description, method, url, headers, body_template, timeout_ms, active, created_at
            """,
            (company_id, bot_id, name, description, method, url,
             json.dumps(headers or {}), json.dumps(body_template) if body_template else None, timeout_ms),
        ).fetchone()
        return dict(row)


def list_actions(company_id: str, bot_id: str | None = None) -> list[dict]:
    with connection() as conn:
        if bot_id:
            rows = conn.execute(
                "SELECT id, name, description, method, url, active, created_at FROM http_actions WHERE company_id = %s AND bot_id = %s ORDER BY created_at",
                (company_id, bot_id),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, name, description, method, url, active, created_at FROM http_actions WHERE company_id = %s ORDER BY created_at",
                (company_id,),
            ).fetchall()
        return [dict(r) for r in rows]


def get_action(company_id: str, action_id: str) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT id, name, description, method, url, headers, body_template, timeout_ms, active FROM http_actions WHERE id = %s AND company_id = %s",
            (action_id, company_id),
        ).fetchone()
        return dict(row) if row else None


def update_action(company_id: str, action_id: str, **updates) -> dict | None:
    allowed = {"name", "description", "method", "url", "headers", "body_template", "timeout_ms", "active"}
    sets = []
    vals = []
    for k, v in updates.items():
        if k not in allowed:
            continue
        if k == "url":
            validate_url(v)
        if k in ("headers", "body_template"):
            sets.append(f"{k} = %s::jsonb")
            vals.append(json.dumps(v))
        else:
            sets.append(f"{k} = %s")
            vals.append(v)
    if not sets:
        return None
    sets.append("updated_at = now()")
    vals.extend([action_id, company_id])
    with connection() as conn:
        row = conn.execute(
            f"UPDATE http_actions SET {', '.join(sets)} WHERE id = %s AND company_id = %s RETURNING id, name, description, method, url, active",
            vals,
        ).fetchone()
        return dict(row) if row else None


def delete_action(company_id: str, action_id: str) -> bool:
    with connection() as conn:
        result = conn.execute(
            "DELETE FROM http_actions WHERE id = %s AND company_id = %s",
            (action_id, company_id),
        )
        return result.rowcount > 0


async def test_action(company_id: str, action_id: str) -> dict:
    """Execute the action with test payload and return the response status/body."""
    action = get_action(company_id, action_id)
    if not action:
        return {"error": "Action not found"}

    try:
        validate_url(action["url"])
    except SSRFBlocked as exc:
        return {"error": f"URL blocked: {exc}"}

    timeout_s = min(action.get("timeout_ms", 5000) / 1000, 10)
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.request(
                method=action["method"],
                url=action["url"],
                headers=action.get("headers") or {},
                json=action.get("body_template") or {"test": True, "source": "knowmivo_test"},
            )
            return {
                "status_code": resp.status_code,
                "body": resp.text[:2000],
                "headers": dict(resp.headers),
            }
    except Exception as exc:
        return {"error": str(exc)}
