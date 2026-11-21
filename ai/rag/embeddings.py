"""Embedding service: batched, provider-agnostic entry point for vectors."""
from ai.llm.client import get_llm_client

BATCH_SIZE = 64  # Azure OpenAI embeddings API practical batch limit


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed texts in batches to respect API limits and keep memory bounded."""
    client = get_llm_client()
    vectors: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        vectors.extend(await client.embed(batch))
    return vectors


async def embed_query(query: str) -> list[float]:
    return (await get_llm_client().embed([query], operation="embed_query"))[0]
