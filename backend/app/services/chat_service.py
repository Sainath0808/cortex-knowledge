"""Chat service: orchestrates guardrails -> agent -> persistence for one turn."""
import json
from collections.abc import AsyncIterator
from uuid import UUID

import structlog
from langchain_core.messages import BaseMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from agents.graph import get_agent
from agents.memory import build_history
from agents.tools import begin_citation_scope, pop_citations
from ai.guardrails.injection import check_input
from ai.guardrails.moderation import StreamingOutputModerator, moderate_output
from ai.guardrails.pii import redact
from app.core.exceptions import GuardrailViolation, InvalidRequest, NotFound, PermissionDenied
from app.core.logging import get_logger
from app.core.telemetry import get_tracer
from app.db.models import Conversation, User
from app.db.repositories.conversations import ConversationRepository
from app.schemas.api import ChatResponse, Citation
from app.services.knowledge_base_service import KnowledgeBaseService

logger = get_logger(__name__)


class ChatService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.conversations = ConversationRepository(db)

    async def _prepare_turn(
        self,
        user: User,
        message: str,
        conversation_id: UUID | None,
        knowledge_base_id: UUID | None,
    ) -> tuple[Conversation, str, list[BaseMessage], UUID | None]:
        verdict = await check_input(message)
        if verdict.blocked:
            raise GuardrailViolation(f"Input blocked: {verdict.reason}")

        redaction = redact(message)
        if redaction.found:
            logger.info("pii_redacted", kinds=redaction.found)
        safe_message = redaction.text

        if conversation_id:
            conversation = await self.conversations.get_with_messages(conversation_id)
            if conversation is None:
                raise NotFound("Conversation not found")
            if conversation.user_id != user.id:
                raise PermissionDenied("Not your conversation")
            if (
                knowledge_base_id is not None
                and conversation.knowledge_base_id != knowledge_base_id
            ):
                raise InvalidRequest(
                    "This conversation belongs to a different knowledge base"
                )
            knowledge_base_id = conversation.knowledge_base_id
        else:
            conversation = await self.conversations.create(
                user.id,
                title=safe_message[:80],
                knowledge_base_id=knowledge_base_id,
            )

        if knowledge_base_id is not None:
            await KnowledgeBaseService(self.db).require_owned(user, knowledge_base_id)

        history = build_history(conversation if conversation_id else None)
        return conversation, safe_message, history, knowledge_base_id

    @staticmethod
    def _agent_input(
        history: list[BaseMessage],
        safe_message: str,
        user_id: UUID,
        knowledge_base_id: UUID | None,
    ) -> dict:
        return {
            "messages": [*history, HumanMessage(content=safe_message)],
            "user_id": str(user_id),
            "knowledge_base_id": (
                str(knowledge_base_id) if knowledge_base_id is not None else None
            ),
            "citations": [],
            "guardrail_blocked": False,
            "tool_call_count": 0,
        }

    async def _complete_turn(
        self, conversation: Conversation, safe_message: str, answer: str
    ) -> ChatResponse:
        citations = [Citation(**citation) for citation in pop_citations()]
        moderated = moderate_output(answer)
        if moderated.flagged:
            logger.warning("output_moderated", reason=moderated.reason)
        answer = moderated.text

        await self.conversations.add_message(conversation.id, "user", safe_message)
        await self.conversations.add_message(
            conversation.id,
            "assistant",
            answer,
            citations=[citation.model_dump() for citation in citations],
        )
        return ChatResponse(
            conversation_id=conversation.id, answer=answer, citations=citations
        )

    async def chat(
        self,
        user: User,
        message: str,
        conversation_id: UUID | None,
        knowledge_base_id: UUID | None = None,
    ) -> ChatResponse:
        structlog.contextvars.bind_contextvars(user_id=str(user.id))
        with get_tracer().start_as_current_span("chat.turn") as span:
            span.set_attribute("user.id", str(user.id))
            conversation, safe_message, history, knowledge_base_id = await self._prepare_turn(
                user, message, conversation_id, knowledge_base_id
            )
            begin_citation_scope()
            state = await get_agent().ainvoke(
                self._agent_input(history, safe_message, user.id, knowledge_base_id)
            )
            return await self._complete_turn(
                conversation, safe_message, str(state["messages"][-1].content)
            )

    async def stream(
        self,
        user: User,
        message: str,
        conversation_id: UUID | None,
        knowledge_base_id: UUID | None = None,
    ) -> AsyncIterator[tuple[str, str]]:
        structlog.contextvars.bind_contextvars(user_id=str(user.id))
        with get_tracer().start_as_current_span("chat.stream") as span:
            span.set_attribute("user.id", str(user.id))
            conversation, safe_message, history, knowledge_base_id = await self._prepare_turn(
                user, message, conversation_id, knowledge_base_id
            )
            begin_citation_scope()
            yield "meta", json.dumps({"conversation_id": str(conversation.id)})

            output_guard = StreamingOutputModerator()
            final_state = None
            streamed_text = False
            streamed_parts: list[str] = []
            reset_sent = False
            async for mode, data in get_agent().astream(
                self._agent_input(history, safe_message, user.id, knowledge_base_id),
                stream_mode=["messages", "values"],
            ):
                if mode == "messages":
                    chunk, metadata = data
                    if metadata.get("langgraph_node") != "agent":
                        continue
                    content = chunk.content
                    if isinstance(content, str) and content:
                        streamed_text = True
                        streamed_parts.append(content)
                        safe_text = output_guard.feed(content)
                        if safe_text:
                            yield "token", safe_text
                        if output_guard.flagged and not reset_sent:
                            yield "reset", output_guard.finish().text
                            reset_sent = True
                elif mode == "values":
                    final_state = data

            if final_state is None:
                raise RuntimeError("The agent completed without returning a final state.")

            answer = str(final_state["messages"][-1].content)
            final_moderation = moderate_output(answer)
            if final_moderation.flagged:
                answer = final_moderation.text
                if not reset_sent:
                    yield "reset", answer
                    reset_sent = True
            elif streamed_text and "".join(streamed_parts) != answer:
                answer = final_moderation.text
                yield "reset", answer
                reset_sent = True
            elif not streamed_text:
                safe_text = output_guard.feed(answer)
                if safe_text:
                    yield "token", safe_text
                remainder = output_guard.finish()
                if remainder.flagged:
                    answer = remainder.text
                    yield "reset", answer
                    reset_sent = True
                elif remainder.text:
                    yield "token", remainder.text
            elif not output_guard.flagged:
                remainder = output_guard.finish()
                if remainder.flagged:
                    answer = remainder.text
                    yield "reset", answer
                    reset_sent = True
                elif remainder.text:
                    yield "token", remainder.text

            result = await self._complete_turn(conversation, safe_message, answer)
            yield "done", json.dumps(
                {
                    "citations": [
                        citation.model_dump() for citation in result.citations
                    ]
                }
            )
