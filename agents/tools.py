"""Agent tools.

Each tool is a typed function the LLM can call. Docstrings matter: the model
reads them to decide when and how to call a tool. Tools validate their own
inputs and always return strings (LLM-readable results, including errors).
"""
import ast
import json
import operator
from contextvars import ContextVar
from typing import Annotated
from uuid import UUID

from app.core.config import get_settings
from app.core.logging import get_logger
from langchain_core.messages import BaseMessage
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState

from ai.rag.pipeline import build_context
from ai.rag.query_rewrite import contextualize_query
from ai.rag.reranker import llm_rerank
from ai.rag.retriever import retrieve

logger = get_logger(__name__)

# Context-local collector avoids mixing citations between simultaneous chat turns.
_citations: ContextVar[list[dict] | None] = ContextVar("chat_citations", default=None)


def begin_citation_scope() -> None:
    _citations.set([])


def pop_citations() -> list[dict]:
    citations = _citations.get() or []
    _citations.set([])
    return citations


@tool
async def knowledge_search(
    query: str,
    user_id: Annotated[str, InjectedState("user_id")],
    messages: Annotated[list[BaseMessage], InjectedState("messages")],
    knowledge_base_id: Annotated[str | None, InjectedState("knowledge_base_id")] = None,
) -> str:
    """Search the organization's knowledge base for information relevant to the query.
    Use this for ANY question about company documents, policies, or internal knowledge.
    Returns the most relevant passages with their chunk ids for citation."""
    settings = get_settings()
    search_query = await contextualize_query(query, messages)
    hits = await retrieve(
        search_query,
        owner_id=UUID(user_id),
        knowledge_base_id=UUID(knowledge_base_id) if knowledge_base_id else None,
        top_k=settings.retrieval_top_k,
    )
    top = await llm_rerank(search_query, hits, top_k=settings.rerank_top_k) if hits else []
    if not top:
        return "No relevant documents found in the knowledge base."
    citations = [
        {
            "document_id": h.document_id,
            "document_title": h.document_title,
            "chunk_id": h.chunk_id,
            "snippet": h.content[:300],
        }
        for h in top
    ]
    collector = _citations.get()
    if collector is not None:
        collector.extend(citations)
    return build_context(top, max_tokens=settings.max_context_tokens)


_SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
}


def _safe_eval(node: ast.AST) -> float:
    """AST-walking evaluator — no eval(), no code execution."""
    match node:
        case ast.Expression():
            return _safe_eval(node.body)
        case ast.Constant() if isinstance(node.value, (int, float)):
            return node.value
        case ast.BinOp() if type(node.op) in _SAFE_OPS:
            return _SAFE_OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
        case ast.UnaryOp() if type(node.op) in _SAFE_OPS:
            return _SAFE_OPS[type(node.op)](_safe_eval(node.operand))
        case _:
            raise ValueError(f"Unsupported expression element: {ast.dump(node)}")


@tool
def calculator(expression: str) -> str:
    """Evaluate a basic arithmetic expression (numbers, + - * / ** %).
    Use for any math the user asks for. Example input: '(120 * 1.08) / 4'."""
    try:
        result = _safe_eval(ast.parse(expression, mode="eval"))
        return str(result)
    except Exception as e:
        return f"Could not evaluate expression: {e}"


@tool
async def knowledge_base_stats(user_id: Annotated[str, InjectedState("user_id")]) -> str:
    """Get statistics about the knowledge base: number of documents and chunks.
    Use when the user asks what's in the knowledge base or how much data is indexed."""
    from app.db.repositories.documents import DocumentRepository
    from app.db.session import async_session_factory

    async with async_session_factory() as session:
        stats = await DocumentRepository(session).stats(UUID(user_id))
    return json.dumps(stats)


ALL_TOOLS = [knowledge_search, calculator, knowledge_base_stats]
