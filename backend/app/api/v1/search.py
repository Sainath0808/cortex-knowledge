"""Semantic search endpoint: raw retrieval without generation."""
from fastapi import APIRouter

from ai.rag.retriever import retrieve
from app.api.deps import DB, CurrentUser
from app.schemas.api import SearchHit, SearchRequest, SearchResponse
from app.services.knowledge_base_service import KnowledgeBaseService

router = APIRouter()


@router.post("", response_model=SearchResponse)
async def semantic_search(payload: SearchRequest, user: CurrentUser, db: DB):
    if payload.knowledge_base_id is not None:
        await KnowledgeBaseService(db).require_owned(user, payload.knowledge_base_id)
    hits = await retrieve(
        payload.query,
        owner_id=user.id,
        knowledge_base_id=payload.knowledge_base_id,
        top_k=payload.top_k,
    )
    return SearchResponse(
        hits=[
            SearchHit(
                chunk_id=h.chunk_id,
                document_id=h.document_id,
                document_title=h.document_title,
                content=h.content,
                score=h.score,
            )
            for h in hits
        ]
    )
