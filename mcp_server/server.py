"""Cortex MCP server.

Exposes the knowledge base as Model Context Protocol tools so ANY MCP-capable
client (Claude Desktop, VS Code, custom agents) can search Cortex without
knowing its internals. This is the same retrieval code the in-process agent
uses — MCP is just a standardized transport for tools.

Run (stdio):  python -m mcp_server.server
"""
import json
from uuid import UUID

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "cortex-knowledge",
    instructions=(
        "Tools for searching the Cortex enterprise knowledge base. "
        "Use knowledge_search for factual questions about indexed documents."
    ),
)


def _configured_owner_id() -> UUID:
    from app.core.config import get_settings

    owner_id = get_settings().mcp_owner_id
    try:
        return UUID(owner_id)
    except ValueError as exc:
        raise RuntimeError("Set MCP_OWNER_ID to the UUID of the service account") from exc


@mcp.tool()
async def knowledge_search(query: str, top_k: int = 5) -> str:
    """Search the Cortex knowledge base and return the most relevant passages.

    Args:
        query: Natural-language search query.
        top_k: Number of passages to return (1-20).
    """
    from ai.rag.retriever import retrieve

    top_k = max(1, min(top_k, 20))
    hits = await retrieve(query, owner_id=_configured_owner_id(), top_k=top_k)
    if not hits:
        return "No relevant documents found."
    return json.dumps(
        [
            {
                "document": h.document_title,
                "chunk_id": h.chunk_id,
                "score": round(h.score, 4),
                "content": h.content,
            }
            for h in hits
        ],
        indent=2,
    )


@mcp.tool()
async def list_documents() -> str:
    """List documents indexed in the Cortex knowledge base with their status."""
    from sqlalchemy import select

    from app.db.models import Document
    from app.db.session import async_session_factory

    async with async_session_factory() as session:
        result = await session.execute(
            select(Document)
            .where(Document.owner_id == _configured_owner_id())
            .order_by(Document.created_at.desc())
            .limit(100)
        )
        docs = result.scalars().all()
    return json.dumps(
        [
            {
                "id": str(d.id),
                "title": d.title,
                "status": d.status.value,
                "chunks": d.chunk_count,
            }
            for d in docs
        ],
        indent=2,
    )


@mcp.resource("cortex://stats")
async def knowledge_stats() -> str:
    """Knowledge base statistics (documents and chunk counts)."""
    from app.db.repositories.documents import DocumentRepository
    from app.db.session import async_session_factory

    async with async_session_factory() as session:
        return json.dumps(
            await DocumentRepository(session).stats(_configured_owner_id())
        )


if __name__ == "__main__":
    mcp.run()  # stdio transport by default
