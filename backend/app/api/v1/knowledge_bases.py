"""Knowledge base management endpoints."""
from uuid import UUID

from fastapi import APIRouter

from app.api.deps import CurrentUser, DB
from app.schemas.api import KnowledgeBaseCreateRequest, KnowledgeBaseOut
from app.services.knowledge_base_service import KnowledgeBaseService

router = APIRouter()


@router.get("", response_model=list[KnowledgeBaseOut])
async def list_knowledge_bases(user: CurrentUser, db: DB):
    return await KnowledgeBaseService(db).list(user)


@router.post("", response_model=KnowledgeBaseOut, status_code=201)
async def create_knowledge_base(
    payload: KnowledgeBaseCreateRequest, user: CurrentUser, db: DB
):
    return await KnowledgeBaseService(db).create(
        user, name=payload.name, description=payload.description
    )


@router.delete("/{knowledge_base_id}", status_code=204)
async def delete_knowledge_base(
    knowledge_base_id: UUID, user: CurrentUser, db: DB
):
    await KnowledgeBaseService(db).delete(user, knowledge_base_id)
