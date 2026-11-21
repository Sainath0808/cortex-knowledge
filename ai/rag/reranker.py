"""Reranking: improve ordering of retrieved chunks before context building.

Two strategies:
1. rrf_merge — Reciprocal Rank Fusion for combining multiple ranked lists
   (e.g., results from two query variants) without score calibration.
2. llm_rerank — pointwise LLM scoring of each chunk against the query.
   More accurate, but adds latency and cost, so it runs on a small candidate
   set after cheap vector search narrows the field.
"""

import asyncio
import json
from dataclasses import replace

from app.core.logging import get_logger

from ai.llm.client import get_llm_client
from ai.llm.prompts import RERANK
from ai.rag.vectorstore import ScoredChunk

logger = get_logger(__name__)


def rrf_merge(result_lists: list[list[ScoredChunk]], *, k: int = 60) -> list[ScoredChunk]:
    """Reciprocal Rank Fusion: score = sum(1 / (k + rank)) across lists."""
    scores: dict[str, float] = {}
    by_id: dict[str, ScoredChunk] = {}
    for results in result_lists:
        for rank, chunk in enumerate(results):
            scores[chunk.chunk_id] = scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank + 1)
            by_id[chunk.chunk_id] = chunk
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    return [replace(by_id[chunk_id], score=score) for chunk_id, score in ordered]


async def llm_rerank(query: str, chunks: list[ScoredChunk], *, top_k: int = 5) -> list[ScoredChunk]:
    """Pointwise LLM reranking; falls back to vector order on failure."""
    client = get_llm_client()

    async def score(chunk: ScoredChunk) -> tuple[ScoredChunk, float]:
        try:
            result = await client.chat(
                [
                    {
                        "role": "user",
                        "content": RERANK.render(query=query, passage=chunk.content[:2000]),
                    }
                ],
                temperature=0.0,
                max_tokens=20,
                response_format={"type": "json_object"},
                operation="rerank",
            )
            return chunk, float(json.loads(result.content)["score"])
        except Exception as e:
            logger.warning("rerank_score_failed", chunk_id=chunk.chunk_id, error=str(e))
            return chunk, chunk.score * 10  # fall back to (scaled) vector score

    scored = await asyncio.gather(*(score(c) for c in chunks))
    ranked = sorted(scored, key=lambda cs: cs[1], reverse=True)
    return [c for c, _ in ranked[:top_k]]
