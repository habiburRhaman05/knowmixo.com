"""Audit event service for Phase 7/8.

Provides centralized audit logging with request_id propagation,
tenant isolation, and safe_metadata allowlist.
"""
import json
import uuid
from contextlib import contextmanager
from typing import Optional

from app.db import connection


class AuditContext:
    """Thread-local audit context for request_id propagation."""

    def __init__(self):
        self._request_id: Optional[str] = None
        self._company_id: Optional[str] = None
        self._actor: Optional[str] = None  # 'visitor' or 'owner'
        self._actor_id: Optional[str] = None

    @property
    def request_id(self) -> str:
        if self._request_id is None:
            self._request_id = str(uuid.uuid4())
        return self._request_id

    @request_id.setter
    def request_id(self, value: str):
        self._request_id = value

    @property
    def company_id(self) -> Optional[str]:
        return self._company_id

    @company_id.setter
    def company_id(self, value: str):
        self._company_id = value

    @property
    def actor(self) -> Optional[str]:
        return self._actor

    @actor.setter
    def actor(self, value: str):
        if value not in ('visitor', 'owner'):
            raise ValueError("actor must be 'visitor' or 'owner'")
        self._actor = value

    @property
    def actor_id(self) -> Optional[str]:
        return self._actor_id

    @actor_id.setter
    def actor_id(self, value: str):
        self._actor_id = value

    def clear(self):
        self._request_id = None
        self._company_id = None
        self._actor = None
        self._actor_id = None


audit_context = AuditContext()


@contextmanager
def audit_request_context(request_id: str, company_id: str, actor: str, actor_id: str):
    """Context manager to set audit context for a request."""
    old_request_id = audit_context._request_id
    old_company_id = audit_context._company_id
    old_actor = audit_context._actor
    old_actor_id = audit_context._actor_id

    try:
        audit_context.request_id = request_id
        audit_context.company_id = company_id
        audit_context.actor = actor
        audit_context.actor_id = actor_id
        yield
    finally:
        audit_context._request_id = old_request_id
        audit_context._company_id = old_company_id
        audit_context._actor = old_actor
        audit_context._actor_id = old_actor_id


def write_audit_event(
    conn,
    action: str,
    target_type: str,
    target_id: Optional[str] = None,
    safe_metadata: Optional[dict] = None,
) -> None:
    """Write an audit event using the current audit context.

    Must be called within an audit_request_context.
    """
    if not audit_context.company_id:
        raise RuntimeError("Audit context not set. Use audit_request_context()")
    if not audit_context.actor:
        raise RuntimeError("Audit actor not set. Use audit_request_context()")
    if not audit_context.actor_id:
        raise RuntimeError("Audit actor_id not set. Use audit_request_context()")

    conn.execute(
        """
        INSERT INTO audit_events (company_id, actor, actor_id, target_id, target_type, action, request_id, safe_metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            audit_context.company_id,
            audit_context.actor,
            audit_context.actor_id,
            target_id,
            target_type,
            action,
            audit_context.request_id,
            json.dumps(safe_metadata or {}),
        ),
    )


def get_request_id() -> str:
    """Get current request_id, generating one if not set."""
    return audit_context.request_id


def set_request_id(request_id: str):
    """Set request_id manually (for testing or external integration)."""
    audit_context.request_id = request_id