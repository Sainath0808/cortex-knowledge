"""arq worker: background ingestion pipeline.

ingest_document: text -> chunk -> embed -> upsert to Qdrant -> mark ready.
Failures mark the document as failed with the error message; arq retries
transient failures automatically.
"""
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


async def ingest_document(ctx: dict, document_id: str, text: str) -> str:
    from uuid import UUID

    from ai.rag.chunking import chunk_document
    from ai.rag.embeddings import embed_texts
    from ai.rag.vectorstore import get_vector_store
    from app.db.models import DocumentStatus
    from app.db.repositories.documents import DocumentRepository
    from app.db.session import async_session_factory

    settings = get_settings()
    doc_uuid = UUID(document_id)
    logger.info("ingest_start", document_id=document_id)

    async with async_session_factory() as session:
        repo = DocumentRepository(session)
        await repo.set_status(doc_uuid, DocumentStatus.processing)
        await session.commit()

    try:
        chunks = await chunk_document(
            text,
            strategy=settings.chunking_strategy,
            max_tokens=settings.chunk_size_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
        )
        if not chunks:
            raise ValueError("Document produced no chunks (empty or unparseable)")

        store = get_vector_store()
        await store.ensure_collection()
        await store.delete_document(document_id)
        async with async_session_factory() as session:
            repo = DocumentRepository(session)
            doc = await repo.get(doc_uuid)
            if doc is None:
                raise ValueError(f"Document {document_id} no longer exists")
            await repo.delete_chunks(doc_uuid)
            rows = await repo.add_chunks(
                doc_uuid,
                [
                    {"chunk_index": c.chunk_index, "content": c.content, "token_count": c.token_count}
                    for c in chunks
                ],
            )
            chunk_ids = [str(r.id) for r in rows]
            title = doc.title
            owner_id = str(doc.owner_id)
            knowledge_base_id = (
                str(doc.knowledge_base_id) if doc.knowledge_base_id else None
            )
            await session.commit()

        vectors = await embed_texts([c.content for c in chunks])
        await store.upsert_chunks(
            chunk_ids=chunk_ids,
            vectors=vectors,
            payloads=[
                {
                    "document_id": document_id,
                    "owner_id": owner_id,
                    "knowledge_base_id": knowledge_base_id,
                    "document_title": title,
                    "content": c.content,
                }
                for c in chunks
            ],
        )

        async with async_session_factory() as session:
            repo = DocumentRepository(session)
            await repo.set_status(doc_uuid, DocumentStatus.ready, chunk_count=len(chunks))
            await session.commit()
        logger.info("ingest_done", document_id=document_id, chunks=len(chunks))
        return f"ingested {len(chunks)} chunks"

    except Exception as e:
        logger.error("ingest_failed", document_id=document_id, error=str(e))
        async with async_session_factory() as session:
            repo = DocumentRepository(session)
            await repo.set_status(doc_uuid, DocumentStatus.failed, error=str(e)[:2000])
            await session.commit()
        raise


async def reindex_document(ctx: dict, document_id: str) -> str:
    from uuid import UUID

    from ai.rag.embeddings import embed_texts
    from ai.rag.vectorstore import get_vector_store
    from app.db.models import DocumentStatus
    from app.db.repositories.documents import DocumentRepository
    from app.db.session import async_session_factory

    doc_uuid = UUID(document_id)
    async with async_session_factory() as session:
        repo = DocumentRepository(session)
        doc = await repo.get(doc_uuid)
        if doc is None:
            raise ValueError(f"Document {document_id} no longer exists")
        chunks = await repo.get_chunks(doc_uuid)
        if not chunks:
            raise ValueError(f"Document {document_id} has no stored chunks to re-index")
        title = doc.title
        owner_id = str(doc.owner_id)
        knowledge_base_id = (
            str(doc.knowledge_base_id) if doc.knowledge_base_id else None
        )
        await repo.set_status(doc_uuid, DocumentStatus.processing)
        await session.commit()

    store = get_vector_store()
    try:
        await store.ensure_collection()
        await store.delete_document(document_id)
        vectors = await embed_texts([chunk.content for chunk in chunks])
        await store.upsert_chunks(
            chunk_ids=[str(chunk.id) for chunk in chunks],
            vectors=vectors,
            payloads=[
                {
                    "document_id": document_id,
                    "owner_id": owner_id,
                    "knowledge_base_id": knowledge_base_id,
                    "document_title": title,
                    "content": chunk.content,
                }
                for chunk in chunks
            ],
        )
        async with async_session_factory() as session:
            await DocumentRepository(session).set_status(
                doc_uuid, DocumentStatus.ready, chunk_count=len(chunks)
            )
            await session.commit()
        logger.info("reindex_done", document_id=document_id, chunks=len(chunks))
        return f"re-indexed {len(chunks)} chunks"
    except Exception as exc:
        logger.error("reindex_failed", document_id=document_id, error=str(exc))
        async with async_session_factory() as session:
            await DocumentRepository(session).set_status(
                doc_uuid, DocumentStatus.failed, error=str(exc)[:2000]
            )
            await session.commit()
        raise


async def startup(ctx: dict) -> None:
    configure_logging()
    logger.info("worker_started")


class WorkerSettings:
    functions = [ingest_document, reindex_document]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_tries = 3
    job_timeout = 600
