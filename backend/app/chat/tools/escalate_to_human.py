"""escalate_to_human tool: triggers an escalation to a human operator."""
import asyncio

from app.chat.tools.registry import ToolDefinition, register_tool
from app.escalation.detector import detect_and_create

TOOL_DEF = ToolDefinition(
    name="escalate_to_human",
    description="Escalate the conversation to a human operator when the AI cannot adequately help.",
    parameters={
        "type": "object",
        "properties": {
            "reason": {"type": "string", "description": "Why the conversation needs human attention."},
            "severity": {
                "type": "string",
                "enum": ["critical", "high", "medium", "low"],
                "description": "Urgency level.",
            },
        },
        "required": ["reason"],
    },
    handler=None,
)


async def _handle(args: dict, context: dict) -> dict:
    scope = context.get("scope")
    if not scope:
        return {"error": "no scope in context"}

    reason = args.get("reason", "Visitor requested human assistance")
    severity = args.get("severity", "medium")

    def _escalate():
        return detect_and_create(
            company_id=scope.company_id,
            conversation_id=scope.conversation_id,
            text=reason,
            intent="action",
            severity=severity,
            ai_summary=f"AI tool-triggered escalation: {reason}",
        )

    escalation_id = await asyncio.to_thread(_escalate)
    if escalation_id:
        return {"escalation_id": escalation_id, "escalated": True, "message": "A human has been notified and will be with you shortly."}
    return {"escalated": False, "message": "An escalation was already in progress for this conversation."}


TOOL_DEF.handler = _handle
register_tool(TOOL_DEF)
