"""Document and chunk repository."""

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentChunk, DocumentStatus


class DocumentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        *,
        owner_id: UUID,
        title: str,
        source_type: str,
        metadata: dict,
        content_sha256: str | None = None,
        knowledge_base_id: UUID | None = None,
    ) -> Document:
        doc = Document(
            owner_id=owner_id,
            knowledge_base_id=knowledge_base_id,
            title=title,
            source_type=source_type,
            doc_metadata=metadata,
            content_sha256=content_sha256,
        )
        self.db.add(doc)
        await self.db.flush()
        return doc

    async def get_by_content_sha256(
        self, owner_id: UUID, content_sha256: str, knowledge_base_id: UUID | None
    ) -> Document | None:
        result = await self.db.execute(
            select(Document).where(
                Document.owner_id == owner_id,
                Document.knowledge_base_id == knowledge_base_id,
                Document.content_sha256 == content_sha256,
            )
        )
        return result.scalar_one_or_none()

    async def get(self, doc_id: UUID) -> Document | None:
        return await self.db.get(Document, doc_id)

    async def list_for_user(
        self, owner_id: UUID, limit: int = 50, knowledge_base_id: UUID | None = None
    ) -> list[Document]:
        statement = select(Document).where(Document.owner_id == owner_id)
        if knowledge_base_id is not None:
            statement = statement.where(Document.knowledge_base_id == knowledge_base_id)
        result = await self.db.execute(statement.order_by(Document.created_at.desc()).limit(limit))
        return list(result.scalars())

    async def set_status(
        self,
        doc_id: UUID,
        status: DocumentStatus,
        *,
        error: str | None = None,
        chunk_count: int | None = None,
    ) -> None:
        doc = await self.db.get(Document, doc_id)
        if doc is None:
            return
        doc.status = status
        doc.error = error
        if chunk_count is not None:
            doc.chunk_count = chunk_count

    async def add_chunks(self, doc_id: UUID, chunks: list[dict]) -> list[DocumentChunk]:
        rows = [
            DocumentChunk(
                document_id=doc_id,
                chunk_index=c["chunk_index"],
                content=c["content"],
                token_count=c["token_count"],
            )
            for c in chunks
        ]
        self.db.add_all(rows)
        await self.db.flush()
        return rows

    async def get_chunks(self, doc_id: UUID) -> list[DocumentChunk]:
        result = await self.db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == doc_id)
            .order_by(DocumentChunk.chunk_index)
        )
        return list(result.scalars())

    async def delete_chunks(self, doc_id: UUID) -> None:
        await self.db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc_id))

    async def stats(self, owner_id: UUID | None = None) -> dict:
        doc_query = select(func.count(Document.id))
        chunk_query = select(func.count(DocumentChunk.id)).join(
            Document, Document.id == DocumentChunk.document_id
        )
        if owner_id is not None:
            doc_query = doc_query.where(Document.owner_id == owner_id)
            chunk_query = chunk_query.where(Document.owner_id == owner_id)
        docs = await self.db.execute(doc_query)
        chunks = await self.db.execute(chunk_query)
        return {"documents": docs.scalar_one(), "chunks": chunks.scalar_one()}
