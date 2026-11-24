"""Audit event service for Phase 7/8.

Provides centralized audit logging with request_id propagation,
tenant isolation, and safe_metadata allowlist.
"""
import json
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional

from app.db import connection


_STATE: ContextVar[dict | None] = ContextVar("audit_state", default=None)


class AuditContext:
    """Per-request audit state held in a ContextVar, so concurrent requests
    (each handled in its own copied context/thread) can never see each
    other's actor, company or request_id."""

    def _state(self) -> dict:
        state = _STATE.get()
        if state is None:
            state = {}
            _STATE.set(state)
        return state

    @property
    def request_id(self) -> str:
        state = self._state()
        if state.get("request_id") is None:
            state["request_id"] = str(uuid.uuid4())
        return state["request_id"]

    @request_id.setter
    def request_id(self, value: str):
        self._state()["request_id"] = value

    @property
    def company_id(self) -> Optional[str]:
        return self._state().get("company_id")

    @company_id.setter
    def company_id(self, value: str):
        self._state()["company_id"] = value

    @property
    def actor(self) -> Optional[str]:
        return self._state().get("actor")

    @actor.setter
    def actor(self, value: str):
        if value not in ("visitor", "owner"):
            raise ValueError("actor must be 'visitor' or 'owner'")
        self._state()["actor"] = value

    @property
    def actor_id(self) -> Optional[str]:
        return self._state().get("actor_id")

    @actor_id.setter
    def actor_id(self, value: str):
        self._state()["actor_id"] = value

    def clear(self):
        _STATE.set({})


audit_context = AuditContext()


@contextmanager
def audit_request_context(request_id: str, company_id: str, actor: str, actor_id: str):
    """Sets a FRESH audit state for the duration of the block and restores
    the previous one afterwards."""
    token = _STATE.set({})
    try:
        audit_context.request_id = request_id
        audit_context.company_id = company_id
        audit_context.actor = actor
        audit_context.actor_id = actor_id
        yield
    finally:
        _STATE.reset(token)


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