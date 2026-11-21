"""Conversation and message repository."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Conversation, Message


class ConversationRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(
        self,
        user_id: UUID,
        title: str = "New conversation",
        knowledge_base_id: UUID | None = None,
    ) -> Conversation:
        conv = Conversation(
            user_id=user_id,
            title=title,
            knowledge_base_id=knowledge_base_id,
        )
        self.db.add(conv)
        await self.db.flush()
        return conv

    async def get_with_messages(self, conv_id: UUID) -> Conversation | None:
        result = await self.db.execute(
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.id == conv_id)
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: UUID, limit: int = 50) -> list[Conversation]:
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars())

    async def add_message(
        self, conv_id: UUID, role: str, content: str, citations: list | None = None
    ) -> Message:
        msg = Message(conversation_id=conv_id, role=role, content=content, citations=citations)
        self.db.add(msg)
        await self.db.flush()
        return msg
