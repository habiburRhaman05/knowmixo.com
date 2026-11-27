"""escalation_contacts CRUD (launch/06-ESCALATION-DESIGN.md §1/§9).
Without verified_at set, the dispatch worker refuses to send to a
contact -- see verification.py for the opt-in code flow that sets it.
"""
from app.db import connection


def create_contact(company_id: str, channel: str, address: str, priority: int, **kwargs) -> dict:
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO escalation_contacts (company_id, channel, address, priority, quiet_hours_tz, quiet_hours_start, quiet_hours_end)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, channel, address, priority, verified_at, active, quiet_hours_tz, quiet_hours_start, quiet_hours_end
            """,
            (
                company_id, channel, address, priority,
                kwargs.get("quiet_hours_tz"), kwargs.get("quiet_hours_start"), kwargs.get("quiet_hours_end"),
            ),
        ).fetchone()
        return dict(row)


def list_contacts(company_id: str) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT id, channel, address, priority, verified_at, active FROM escalation_contacts WHERE company_id = %s ORDER BY priority",
            (company_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_contact(company_id: str, contact_id: str) -> dict | None:
    with connection() as conn:
        row = conn.execute(
            "SELECT id, channel, address, priority, verified_at, active FROM escalation_contacts WHERE id = %s AND company_id = %s",
            (contact_id, company_id),
        ).fetchone()
        return dict(row) if row else None


def update_contact(company_id: str, contact_id: str, **updates) -> dict | None:
    allowed = {"priority", "active", "quiet_hours_tz", "quiet_hours_start", "quiet_hours_end"}
    sets = []
    vals = []
    for k, v in updates.items():
        if k in allowed:
            sets.append(f"{k} = %s")
            vals.append(v)
    if not sets:
        return None
    vals.extend([contact_id, company_id])
    with connection() as conn:
        row = conn.execute(
            f"UPDATE escalation_contacts SET {', '.join(sets)} WHERE id = %s AND company_id = %s RETURNING id, channel, address, priority, verified_at, active",
            vals,
        ).fetchone()
        return dict(row) if row else None


def delete_contact(company_id: str, contact_id: str) -> bool:
    with connection() as conn:
        result = conn.execute(
            "DELETE FROM escalation_contacts WHERE id = %s AND company_id = %s",
            (contact_id, company_id),
        )
        return result.rowcount > 0
