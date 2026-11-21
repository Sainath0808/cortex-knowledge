"""End-to-end RAG pipeline: retrieve -> rerank -> build context -> generate.

This is the deterministic RAG path used both directly (search/QA endpoint)
and by the agent's knowledge_search tool.
"""
from dataclasses import dataclass, field
from uuid import UUID

from ai.llm.client import get_llm_client
from ai.llm.prompts import RAG_ANSWER
from ai.rag.chunking import count_tokens
from ai.rag.reranker import llm_rerank
from ai.rag.retriever import retrieve
from ai.rag.vectorstore import ScoredChunk
from app.core.config import get_settings
from app.core.telemetry import get_tracer


@dataclass
class RAGResult:
    answer: str
    chunks: list[ScoredChunk] = field(default_factory=list)
    usage: dict = field(default_factory=dict)


def build_context(chunks: list[ScoredChunk], *, max_tokens: int) -> str:
    """Concatenate chunks under a token budget, most relevant first."""
    parts: list[str] = []
    used = 0
    for chunk in chunks:
        block = f"[{chunk.chunk_id}] (from: {chunk.document_title})\n{chunk.content}"
        tokens = count_tokens(block)
        if used + tokens > max_tokens:
            break
        parts.append(block)
        used += tokens
    return "\n\n---\n\n".join(parts)


async def answer_query(
    query: str,
    *,
    owner_id: UUID,
    knowledge_base_id: UUID | None = None,
    document_ids: list[str] | None = None,
    use_llm_rerank: bool = True,
) -> RAGResult:
    settings = get_settings()
    with get_tracer().start_as_current_span("rag.answer_query"):
        candidates = await retrieve(
            query,
            owner_id=owner_id,
            knowledge_base_id=knowledge_base_id,
            document_ids=document_ids,
        )
        if not candidates:
            return RAGResult(
                answer="I couldn't find anything relevant in the knowledge base.", chunks=[]
            )

        if use_llm_rerank:
            top_chunks = await llm_rerank(query, candidates, top_k=settings.rerank_top_k)
        else:
            top_chunks = candidates[: settings.rerank_top_k]

        context = build_context(top_chunks, max_tokens=settings.max_context_tokens)
        result = await get_llm_client().chat(
            [
                {"role": "user", "content": RAG_ANSWER.render(context=context, question=query)},
            ],
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_completion_tokens,
            operation="rag_answer",
        )
        return RAGResult(
            answer=result.content or "",
            chunks=top_chunks,
            usage={
                "prompt_tokens": result.prompt_tokens,
                "completion_tokens": result.completion_tokens,
                "cost_usd": round(result.cost_usd, 6),
                "latency_ms": round(result.latency_ms, 1),
            },
        )
