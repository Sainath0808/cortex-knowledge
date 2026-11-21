"""Job queue interface (arq over Redis).

Ingestion is async because chunking + embedding a large PDF can take minutes;
the API must respond immediately and the worker does the heavy lifting.
"""
from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings

_pool = None


async def get_queue():
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    return _pool


async def enqueue_ingestion(document_id: str, text: str) -> None:
    queue = await get_queue()
    await queue.enqueue_job("ingest_document", document_id, text)


async def enqueue_reindex(document_id: str) -> None:
    queue = await get_queue()
    await queue.enqueue_job("reindex_document", document_id)
