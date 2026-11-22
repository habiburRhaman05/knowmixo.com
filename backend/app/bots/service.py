"""Minimal bot provisioning for Phase 3. Full draft-config/publish
management is Phase 4 (docs/19-BACKEND-SPRINT-PLAN-V2.md) -- this exists
now only because documents.bot_id is NOT NULL and V1 is one bot per
company (docs/README.md scope decision), so sources need *some* bot row
to attach to before Phase 4 builds real bot configuration endpoints.
"""
import secrets


def get_or_create_bot_for_company(conn, company_id: str) -> str:
    existing = conn.execute("SELECT id FROM bots WHERE company_id = %s", (company_id,)).fetchone()
    if existing:
        return str(existing["id"])

    public_id = secrets.token_urlsafe(12)
    row = conn.execute(
        "INSERT INTO bots (company_id, public_id) VALUES (%s, %s) RETURNING id",
        (company_id, public_id),
    ).fetchone()
    return str(row["id"])
