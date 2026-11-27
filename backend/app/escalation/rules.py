"""Escalation rules CRUD and matcher (launch/06-ESCALATION-DESIGN.md §2).
Rules are per-company, evaluated on each turn — first match wins.
"""
import json
import logging
import re

from app.db import connection

log = logging.getLogger(__name__)


def create_rule(company_id: str, name: str, match: dict, severity: str) -> dict:
    with connection() as conn:
        row = conn.execute(
            """
            INSERT INTO escalation_rules (company_id, name, match, severity)
            VALUES (%s, %s, %s::jsonb, %s)
            RETURNING id, name, match, severity, active, created_at
            """,
            (company_id, name, json.dumps(match), severity),
        ).fetchone()
        return dict(row)


def list_rules(company_id: str) -> list[dict]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT id, name, match, severity, active, created_at FROM escalation_rules WHERE company_id = %s ORDER BY created_at",
            (company_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def update_rule(company_id: str, rule_id: str, **updates) -> dict | None:
    allowed = {"name", "match", "severity", "active"}
    sets = []
    vals = []
    for k, v in updates.items():
        if k not in allowed:
            continue
        if k == "match":
            sets.append("match = %s::jsonb")
            vals.append(json.dumps(v))
        else:
            sets.append(f"{k} = %s")
            vals.append(v)
    if not sets:
        return None
    vals.extend([rule_id, company_id])
    with connection() as conn:
        row = conn.execute(
            f"UPDATE escalation_rules SET {', '.join(sets)} WHERE id = %s AND company_id = %s RETURNING id, name, match, severity, active, created_at",
            vals,
        ).fetchone()
        return dict(row) if row else None


def delete_rule(company_id: str, rule_id: str) -> bool:
    with connection() as conn:
        result = conn.execute(
            "DELETE FROM escalation_rules WHERE id = %s AND company_id = %s",
            (rule_id, company_id),
        )
        return result.rowcount > 0


def evaluate_rules(company_id: str, text: str, intent: str, severity: str) -> dict | None:
    """Evaluate all active rules for a company against the turn. First match wins."""
    rules = list_rules(company_id)
    for rule in rules:
        if not rule.get("active"):
            continue
        if _matches(rule["match"], text, intent, severity):
            return rule
    return None


def _matches(match: dict, text: str, intent: str, severity: str) -> bool:
    text_lower = text.lower()
    keywords = match.get("keywords") or []
    if keywords and not any(kw.lower() in text_lower for kw in keywords):
        return False

    intents = match.get("intents") or []
    if intents and intent not in intents:
        return False

    severity_min = match.get("severity_min")
    if severity_min:
        severity_order = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        if severity_order.get(severity, 0) < severity_order.get(severity_min, 0):
            return False

    return True
