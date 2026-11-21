"""Backfill owner_id payloads for existing Qdrant points before scoped retrieval."""
import asyncio

from app.db.models import Document
from app.db.session import async_session_factory
from sqlalchemy import select

from ai.rag.vectorstore import get_vector_store


async def main() -> None:
    store = get_vector_store()
    await store.ensure_collection()
    async with async_session_factory() as session:
        result = await session.execute(
            select(Document.id, Document.owner_id, Document.knowledge_base_id)
        )
        documents = result.all()

    updated = 0
    for document_id, owner_id, knowledge_base_id in documents:
        await store.set_document_owner(
            str(document_id),
            str(owner_id),
            str(knowledge_base_id) if knowledge_base_id else None,
        )
        updated += 1
    print(f"Backfilled owner metadata for {updated} documents.")


if __name__ == "__main__":
    asyncio.run(main())
