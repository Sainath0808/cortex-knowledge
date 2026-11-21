"""BM25 lexical retrieval over the caller's authorized PostgreSQL chunks."""
import math
import re
from collections import Counter
from uuid import UUID

from ai.rag.vectorstore import ScoredChunk

TOKEN_PATTERN = re.compile(r"[a-z0-9]+", re.IGNORECASE)
MAX_CORPUS_CHUNKS = 10_000
BM25_K1 = 1.5
BM25_B = 0.75


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def rank_bm25(
    query: str, chunks: list[ScoredChunk], *, top_k: int
) -> list[ScoredChunk]:
    """Rank a bounded in-memory chunk set with Okapi BM25."""
    query_terms = _tokens(query)
    if not query_terms or not chunks or top_k <= 0:
        return []

    documents = [_tokens(chunk.content) for chunk in chunks]
    average_length = sum(map(len, documents)) / len(documents)
    if average_length == 0:
        return []

    document_frequencies = Counter(
        term for document in documents for term in set(document)
    )
    ranked: list[tuple[float, ScoredChunk]] = []
    for chunk, tokens in zip(chunks, documents, strict=True):
        term_frequencies = Counter(tokens)
        length_normalizer = BM25_K1 * (
            1 - BM25_B + BM25_B * len(tokens) / average_length
        )
        score = 0.0
        for term in query_terms:
            frequency = term_frequencies[term]
            if not frequency:
                continue
            frequency_in_corpus = document_frequencies[term]
            inverse_document_frequency = math.log(
                1
                + (len(documents) - frequency_in_corpus + 0.5)
                / (frequency_in_corpus + 0.5)
            )
            score += (
                inverse_document_frequency
                * frequency
                * (BM25_K1 + 1)
                / (frequency + length_normalizer)
            )
        if score > 0:
            ranked.append((score, chunk))

    ranked.sort(key=lambda result: result[0], reverse=True)
    return [
        ScoredChunk(
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            document_title=chunk.document_title,
            content=chunk.content,
            score=score,
        )
        for score, chunk in ranked[:top_k]
    ]


async def search_bm25(
    query: str,
    *,
    owner_id: UUID,
    knowledge_base_id: UUID | None = None,
    top_k: int,
    document_ids: list[str] | None = None,
) -> list[ScoredChunk]:
    from app.db.models import Document, DocumentChunk, DocumentStatus
    from app.db.session import async_session_factory
    from sqlalchemy import select

    statement = (
        select(DocumentChunk, Document.title)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(Document.owner_id == owner_id, Document.status == DocumentStatus.ready)
        .order_by(DocumentChunk.id)
        .limit(MAX_CORPUS_CHUNKS)
    )
    if document_ids:
        statement = statement.where(Document.id.in_([UUID(value) for value in document_ids]))
    if knowledge_base_id is not None:
        statement = statement.where(Document.knowledge_base_id == knowledge_base_id)

    async with async_session_factory() as session:
        result = await session.execute(statement)
        chunks = [
            ScoredChunk(
                chunk_id=str(chunk.id),
                document_id=str(chunk.document_id),
                document_title=title,
                content=chunk.content,
                score=0.0,
            )
            for chunk, title in result.all()
        ]
    return rank_bm25(query, chunks, top_k=top_k)
