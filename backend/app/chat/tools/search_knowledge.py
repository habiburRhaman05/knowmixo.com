"""search_knowledge tool: performs a RAG retrieval within the conversation scope.
Used when the LLM needs to search for additional information mid-turn.
"""
import asyncio

from app.chat.rag_v2.base import Passage, Scope
from app.chat.rag_v2.stages import retrieve
from app.chat.tools.registry import ToolDefinition, register_tool
from app.db import connection

TOOL_DEF = ToolDefinition(
    name="search_knowledge",
    description="Search the knowledge base for information relevant to the visitor's question.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query."},
        },
        "required": ["query"],
    },
    handler=None,  # set below
)


async def _handle(args: dict, context: dict) -> dict:
    query = args.get("query", "")
    if not query:
        return {"passages": [], "error": "query is required"}

    scope = context.get("scope")
    if not scope:
        return {"passages": [], "error": "no scope in context"}

    def _search():
        with connection() as conn:
            passages = retrieve.retrieve(conn, scope, query)
            return [
                {"title": p.title, "text": p.text[:500], "page": p.page}
                for p in passages[:5]
            ]

    results = await asyncio.to_thread(_search)
    return {"passages": results}


TOOL_DEF.handler = _handle
register_tool(TOOL_DEF)
