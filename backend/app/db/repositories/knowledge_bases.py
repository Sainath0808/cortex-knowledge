"""Persistence operations for user-owned knowledge bases."""
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, KnowledgeBase


class KnowledgeBaseRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, *, owner_id: UUID, name: str, description: str) -> KnowledgeBase:
        knowledge_base = KnowledgeBase(
            owner_id=owner_id,
            name=name,
            description=description,
        )
        self.db.add(knowledge_base)
        await self.db.flush()
        return knowledge_base

    async def get(self, knowledge_base_id: UUID) -> KnowledgeBase | None:
        return await self.db.get(KnowledgeBase, knowledge_base_id)

    async def list_for_owner(self, owner_id: UUID) -> list[dict]:
        statement = (
            select(
                KnowledgeBase,
                func.count(Document.id).label("document_count"),
            )
            .outerjoin(Document, Document.knowledge_base_id == KnowledgeBase.id)
            .where(KnowledgeBase.owner_id == owner_id)
            .group_by(KnowledgeBase.id)
            .order_by(KnowledgeBase.created_at.desc())
        )
        result = await self.db.execute(statement)
        return [
            {"knowledge_base": knowledge_base, "document_count": count}
            for knowledge_base, count in result.all()
        ]

    async def document_count(self, knowledge_base_id: UUID) -> int:
        result = await self.db.execute(
            select(func.count(Document.id)).where(
                Document.knowledge_base_id == knowledge_base_id
            )
        )
        return result.scalar_one()

    async def delete(self, knowledge_base: KnowledgeBase) -> None:
        await self.db.delete(knowledge_base)
