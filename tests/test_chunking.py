"""Chunking tests: token budgets, overlap, strategy behavior, and edge cases."""
from unittest.mock import AsyncMock, patch

from ai.rag.chunking import (
    chunk_fixed,
    chunk_semantic,
    chunk_structure_aware,
    chunk_text,
    count_tokens,
)


def test_short_text_single_chunk():
    chunks = chunk_text("Hello world. This is a short document.", max_tokens=512)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0


def test_chunks_respect_token_budget():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 100 for i in range(20))
    chunks = chunk_text(text, max_tokens=128, overlap_tokens=16)
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.token_count <= 128 + 16  # budget plus carried overlap


def test_overlap_carries_content():
    text = "\n\n".join(f"Sentence number {i} content." for i in range(60))
    chunks = chunk_text(text, max_tokens=64, overlap_tokens=16)
    assert len(chunks) >= 2
    # Some trailing content of chunk N appears in chunk N+1.
    tail_unit = chunks[0].content.split("\n\n")[-1]
    assert tail_unit in chunks[1].content


def test_pathological_no_punctuation():
    text = "token " * 3000
    chunks = chunk_text(text, max_tokens=100, overlap_tokens=10)
    assert all(c.token_count <= 200 for c in chunks)
    assert len(chunks) > 5


def test_empty_text():
    assert chunk_text("") == []


def test_count_tokens_positive():
    assert count_tokens("hello world") >= 2


def test_fixed_chunking_respects_token_window_and_overlap():
    chunks = chunk_fixed("word " * 120, max_tokens=32, overlap_tokens=8)

    assert len(chunks) > 1
    assert all(chunk.token_count <= 32 for chunk in chunks)
    assert chunks[0].content.split()[-8:] == chunks[1].content.split()[:8]


def test_structure_aware_repeats_section_heading():
    chunks = chunk_structure_aware(
        "# Security\n\n" + "Security policy details. " * 30 + "\n\n# Support\n\nContact support.",
        max_tokens=32,
        overlap_tokens=4,
    )

    assert any(chunk.content.startswith("# Security") for chunk in chunks)
    assert any(chunk.content.startswith("# Support") for chunk in chunks)
    assert all(chunk.token_count <= 32 for chunk in chunks)


async def test_semantic_chunking_splits_at_embedding_distance():
    vectors = [[1.0, 0.0], [1.0, 0.0], [0.0, 1.0]]
    with patch("ai.rag.embeddings.embed_texts", new=AsyncMock(return_value=vectors)):
        chunks = await chunk_semantic(
            "Policy allows remote work. Teams set schedules. Product ships monthly.",
            max_tokens=32,
            overlap_tokens=2,
            similarity_threshold=0.7,
        )

    assert len(chunks) == 2
    assert "Teams set schedules." in chunks[0].content
    assert "Product ships monthly." in chunks[1].content
