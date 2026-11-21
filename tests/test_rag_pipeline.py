"""RAG pipeline tests with faked retrieval and LLM."""
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from ai.llm.client import ChatResult
from ai.rag.bm25 import rank_bm25
from ai.rag.pipeline import answer_query, build_context
from ai.rag.reranker import rrf_merge
from ai.rag.vectorstore import ScoredChunk


def test_build_context_respects_budget(fake_chunks):
    context = build_context(fake_chunks, max_tokens=40)
    assert "chunk-0" in context
    assert len(context) < sum(len(c.content) for c in fake_chunks)


def test_build_context_includes_citations_and_titles(fake_chunks):
    context = build_context(fake_chunks, max_tokens=10_000)
    assert "[chunk-0]" in context and "Doc 0" in context


def test_rrf_merge_prefers_consistent_chunks(fake_chunks):
    list_a = fake_chunks[:3]  # chunk-0,1,2
    list_b = [fake_chunks[1], fake_chunks[0], fake_chunks[4]]
    merged = rrf_merge([list_a, list_b])
    assert merged[0].chunk_id in {"chunk-0", "chunk-1"}
    assert len(merged) == 4


def test_bm25_prioritizes_exact_lexical_match():
    chunks = [
        ScoredChunk("1", "doc-1", "Policy", "JWT token rotation requires 90 days.", 0),
        ScoredChunk("2", "doc-2", "Guide", "The service uses a credential lifecycle.", 0),
    ]

    results = rank_bm25("JWT token rotation", chunks, top_k=2)

    assert results[0].chunk_id == "1"


async def test_answer_query_no_hits_returns_honest_answer():
    with patch("ai.rag.pipeline.retrieve", new=AsyncMock(return_value=[])):
        result = await answer_query("unknown question", owner_id=uuid4())
    assert "couldn't find" in result.answer.lower()
    assert result.chunks == []


async def test_answer_query_generates_with_context(fake_chunks):
    fake_llm = AsyncMock()
    fake_llm.chat = AsyncMock(
        return_value=ChatResult(
            content="Remote work is allowed 3 days per week [chunk-0].",
            model="gpt-4o",
            prompt_tokens=500,
            completion_tokens=20,
            cost_usd=0.001,
        )
    )
    with (
        patch("ai.rag.pipeline.retrieve", new=AsyncMock(return_value=fake_chunks)),
        patch("ai.rag.pipeline.get_llm_client", return_value=fake_llm),
    ):
        result = await answer_query(
            "What is the remote work policy?", owner_id=uuid4(), use_llm_rerank=False
        )

    assert "[chunk-0]" in result.answer
    assert result.usage["prompt_tokens"] == 500
    sent_prompt = fake_llm.chat.call_args[0][0][0]["content"]
    assert "remote work policy" in sent_prompt.lower()
