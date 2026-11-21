"""Qdrant vector store adapter.

Vectors live in Qdrant; canonical chunk text and metadata live in Postgres.
Qdrant payloads carry enough metadata (document_id, title, content) to build
answers without a Postgres round-trip on the hot path.
"""
from dataclasses import dataclass
from functools import lru_cache

from qdrant_client import AsyncQdrantClient, models

from app.core.config import get_settings


@dataclass
class ScoredChunk:
    chunk_id: str
    document_id: str
    document_title: str
    content: str
    score: float


class QdrantStore:
    def __init__(self):
        s = get_settings()
        self.client = AsyncQdrantClient(url=s.qdrant_url)
        self.collection = s.qdrant_collection
        self.dimensions = s.embedding_dimensions
        self._indexes_ready = False

    async def ensure_collection(self) -> None:
        if self._indexes_ready:
            return
        if not await self.client.collection_exists(self.collection):
            await self.client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(
                    size=self.dimensions, distance=models.Distance.COSINE
                ),
            )
        # Payload index speeds up filtered search by document_id.
        for field_name in ("document_id", "owner_id", "knowledge_base_id"):
            await self.client.create_payload_index(
                collection_name=self.collection,
                field_name=field_name,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )
        self._indexes_ready = True

    async def upsert_chunks(
        self,
        *,
        chunk_ids: list[str],
        vectors: list[list[float]],
        payloads: list[dict],
    ) -> None:
        await self.client.upsert(
            collection_name=self.collection,
            points=models.Batch(ids=chunk_ids, vectors=vectors, payloads=payloads),
        )

    async def search(
        self,
        vector: list[float],
        *,
        owner_id: str,
        knowledge_base_id: str | None = None,
        top_k: int = 10,
        document_ids: list[str] | None = None,
    ) -> list[ScoredChunk]:
        conditions = [
            models.FieldCondition(
                key="owner_id", match=models.MatchValue(value=owner_id)
            )
        ]
        if knowledge_base_id is not None:
            conditions.append(
                models.FieldCondition(
                    key="knowledge_base_id",
                    match=models.MatchValue(value=knowledge_base_id),
                )
            )
        if document_ids:
            conditions.append(
                models.FieldCondition(
                    key="document_id", match=models.MatchAny(any=document_ids)
                )
            )
        query_filter = models.Filter(must=conditions)
        result = await self.client.query_points(
            collection_name=self.collection,
            query=vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )
        return [
            ScoredChunk(
                chunk_id=str(p.id),
                document_id=p.payload.get("document_id", ""),
                document_title=p.payload.get("document_title", ""),
                content=p.payload.get("content", ""),
                score=p.score,
            )
            for p in result.points
        ]

    async def delete_document(self, document_id: str) -> None:
        await self.client.delete(
            collection_name=self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id", match=models.MatchValue(value=document_id)
                        )
                    ]
                )
            ),
        )

    async def set_document_owner(
        self, document_id: str, owner_id: str, knowledge_base_id: str | None = None
    ) -> None:
        await self.client.set_payload(
            collection_name=self.collection,
            payload={
                "owner_id": owner_id,
                "knowledge_base_id": knowledge_base_id,
            },
            points=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        )
                    ]
                )
            ),
        )


@lru_cache
def get_vector_store() -> QdrantStore:
    return QdrantStore()
