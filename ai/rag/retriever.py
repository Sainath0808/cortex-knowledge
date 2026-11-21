"""Retriever: query -> embedding -> vector search -> scored chunks."""
import asyncio
from uuid import UUID

from app.core.config import get_settings
from app.core.telemetry import get_tracer

from ai.rag.bm25 import search_bm25
from ai.rag.embeddings import embed_query
from ai.rag.reranker import rrf_merge
from ai.rag.vectorstore import ScoredChunk, get_vector_store


async def retrieve(
    query: str,
    *,
    owner_id: UUID,
    knowledge_base_id: UUID | None = None,
    top_k: int | None = None,
    document_ids: list[str] | None = None,
) -> list[ScoredChunk]:
    settings = get_settings()
    k = top_k or settings.retrieval_top_k
    with get_tracer().start_as_current_span("rag.retrieve") as span:
        span.set_attribute("rag.top_k", k)
        vector = await embed_query(query)
        dense_hits, lexical_hits = await asyncio.gather(
            get_vector_store().search(
                vector,
                owner_id=str(owner_id),
                knowledge_base_id=str(knowledge_base_id) if knowledge_base_id else None,
                top_k=k,
                document_ids=document_ids,
            ),
            search_bm25(
                query,
                owner_id=owner_id,
                knowledge_base_id=knowledge_base_id,
                top_k=k,
                document_ids=document_ids,
            ),
        )
        hits = rrf_merge([dense_hits, lexical_hits])[:k]
        span.set_attribute("rag.dense_hits", len(dense_hits))
        span.set_attribute("rag.lexical_hits", len(lexical_hits))
        span.set_attribute("rag.fused_hits", len(hits))
        return hits
