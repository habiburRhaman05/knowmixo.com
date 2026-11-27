"""Tool registry: maps tool names to their definitions and handlers.
Each tool has a schema (for the LLM) and an execute function (for the runtime).
"""
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

log = logging.getLogger(__name__)

ToolHandler = Callable[..., Coroutine[Any, Any, dict]]


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict
    handler: ToolHandler
    requires_conn: bool = False


_REGISTRY: dict[str, ToolDefinition] = {}


def register_tool(tool: ToolDefinition) -> None:
    _REGISTRY[tool.name] = tool


def get_tool(name: str) -> ToolDefinition | None:
    return _REGISTRY.get(name)


def list_tools() -> list[dict]:
    return [
        {"name": t.name, "description": t.description, "parameters": t.parameters}
        for t in _REGISTRY.values()
    ]


def tool_catalog_for_scope(scope_features: dict | None = None) -> list[dict]:
    """Returns the tool catalog suitable for inclusion in the system prompt."""
    return list_tools()


async def execute_tool(name: str, args: dict, context: dict) -> dict:
    """Execute a registered tool. Returns {result: ..., error: ...}."""
    tool = get_tool(name)
    if not tool:
        return {"error": f"Unknown tool: {name}"}
    try:
        result = await tool.handler(args=args, context=context)
        return {"result": result}
    except Exception as exc:
        log.exception("tool %s failed", name)
        return {"error": str(exc)}
