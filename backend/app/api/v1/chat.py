"""Chat endpoints: agentic chat (with streaming variant) + conversation history."""
import json
from uuid import UUID

from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.api.deps import DB, CurrentUser
from app.core.exceptions import CortexError, NotFound, PermissionDenied
from app.core.logging import get_logger
from app.db.repositories.conversations import ConversationRepository
from app.schemas.api import ChatRequest, ChatResponse
from app.services.chat_service import ChatService

router = APIRouter()
logger = get_logger(__name__)


@router.post("", response_model=ChatResponse)
async def chat(payload: ChatRequest, user: CurrentUser, db: DB):
    return await ChatService(db).chat(
        user,
        payload.message,
        payload.conversation_id,
        payload.knowledge_base_id,
    )


@router.post("/stream")
async def chat_stream(payload: ChatRequest, user: CurrentUser, db: DB):
    """Stream agent-generated text and citations as server-sent events."""

    async def event_generator():
        try:
            async for event, data in ChatService(db).stream(
                user,
                payload.message,
                payload.conversation_id,
                payload.knowledge_base_id,
            ):
                yield {"event": event, "data": data}
        except CortexError as exc:
            yield {"event": "error", "data": json.dumps({"detail": exc.detail})}
        except Exception:
            logger.exception("chat_stream_failed")
            yield {
                "event": "error",
                "data": json.dumps({"detail": "Chat stream failed. Please retry."}),
            }

    return EventSourceResponse(event_generator())


@router.get("/conversations")
async def list_conversations(user: CurrentUser, db: DB):
    convs = await ConversationRepository(db).list_for_user(user.id)
    return [
        {
            "id": str(conversation.id),
            "title": conversation.title,
            "knowledge_base_id": (
                str(conversation.knowledge_base_id)
                if conversation.knowledge_base_id
                else None
            ),
            "created_at": conversation.created_at.isoformat(),
        }
        for conversation in convs
    ]


@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: UUID, user: CurrentUser, db: DB):
    conv = await ConversationRepository(db).get_with_messages(conv_id)
    if conv is None:
        raise NotFound("Conversation not found")
    if conv.user_id != user.id:
        raise PermissionDenied("Not your conversation")
    return {
        "id": str(conv.id),
        "title": conv.title,
        "knowledge_base_id": (
            str(conv.knowledge_base_id) if conv.knowledge_base_id else None
        ),
        "messages": [
            {"role": m.role, "content": m.content, "citations": m.citations} for m in conv.messages
        ],
    }
