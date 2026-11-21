"""Knowledge base lifecycle and ownership checks."""
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidRequest, NotFound, PermissionDenied
from app.db.models import KnowledgeBase, User
from app.db.repositories.knowledge_bases import KnowledgeBaseRepository


class KnowledgeBaseService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repository = KnowledgeBaseRepository(db)

    async def list(self, user: User) -> list[dict]:
        rows = await self.repository.list_for_owner(user.id)
        return [
            {
                "id": str(row["knowledge_base"].id),
                "name": row["knowledge_base"].name,
                "description": row["knowledge_base"].description,
                "document_count": row["document_count"],
                "created_at": row["knowledge_base"].created_at,
            }
            for row in rows
        ]

    async def create(self, user: User, *, name: str, description: str) -> KnowledgeBase:
        normalized_name = name.strip()
        if not normalized_name:
            raise InvalidRequest("Knowledge base name cannot be empty")
        knowledge_base = await self.repository.create(
            owner_id=user.id,
            name=normalized_name,
            description=description.strip(),
        )
        try:
            await self.db.commit()
        except IntegrityError as exc:
            await self.db.rollback()
            raise InvalidRequest("A knowledge base with this name already exists") from exc
        await self.db.refresh(knowledge_base)
        return knowledge_base

    async def require_owned(self, user: User, knowledge_base_id: UUID) -> KnowledgeBase:
        knowledge_base = await self.repository.get(knowledge_base_id)
        if knowledge_base is None:
            raise NotFound("Knowledge base not found")
        if knowledge_base.owner_id != user.id:
            raise PermissionDenied("Not your knowledge base")
        return knowledge_base

    async def delete(self, user: User, knowledge_base_id: UUID) -> None:
        knowledge_base = await self.require_owned(user, knowledge_base_id)
        if await self.repository.document_count(knowledge_base.id):
            raise InvalidRequest("Move or delete its documents before deleting this knowledge base")
        await self.repository.delete(knowledge_base)
        await self.db.commit()
