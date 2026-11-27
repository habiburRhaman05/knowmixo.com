"""capture_lead tool: captures visitor lead information during conversation."""
import asyncio
import json

from app.chat.tools.registry import ToolDefinition, register_tool
from app.db import connection

TOOL_DEF = ToolDefinition(
    name="capture_lead",
    description="Capture a visitor's contact information (name, email, phone) as a lead.",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Visitor's name."},
            "email": {"type": "string", "description": "Visitor's email address."},
            "phone": {"type": "string", "description": "Visitor's phone number."},
            "notes": {"type": "string", "description": "Additional context from the conversation."},
        },
        "required": [],
    },
    handler=None,
)


async def _handle(args: dict, context: dict) -> dict:
    scope = context.get("scope")
    if not scope:
        return {"error": "no scope in context"}

    name = args.get("name", "")
    email = args.get("email", "")
    phone = args.get("phone", "")
    notes = args.get("notes", "")

    if not name and not email and not phone:
        return {"error": "at least one of name, email, or phone is required"}

    def _save():
        with connection() as conn:
            row = conn.execute(
                """
                INSERT INTO leads (company_id, bot_id, conversation_id, name, email, phone, notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (scope.company_id, scope.bot_id, scope.conversation_id,
                 name or None, email or None, phone or None, notes or None),
            ).fetchone()
            return str(row["id"]) if row else None

    try:
        lead_id = await asyncio.to_thread(_save)
        return {"lead_id": lead_id, "captured": True}
    except Exception as exc:
        return {"error": f"Failed to capture lead: {exc}"}


TOOL_DEF.handler = _handle
register_tool(TOOL_DEF)
