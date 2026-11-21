"""Conversation-aware query rewriting for follow-up retrieval."""
from app.core.config import get_settings
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from ai.llm.client import get_llm_client
from ai.llm.prompts import CONTEXTUALIZE_QUERY


def _message_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return " ".join(
            block["text"]
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        ).strip()
    return ""


def _prior_turns(messages: list[BaseMessage]) -> str:
    latest_user_index = next(
        (index for index in range(len(messages) - 1, -1, -1)
         if isinstance(messages[index], HumanMessage)),
        len(messages),
    )
    turns: list[str] = []
    for message in messages[:latest_user_index]:
        if isinstance(message, HumanMessage):
            role = "User"
        elif isinstance(message, AIMessage) and not message.tool_calls:
            role = "Assistant"
        else:
            continue
        text = _message_text(message.content)
        if text:
            turns.append(f"{role}: {text[:1200]}")
    return "\n".join(turns[-6:])


async def contextualize_query(query: str, messages: list[BaseMessage]) -> str:
    """Resolve follow-up references without changing retrieval authorization."""
    settings = get_settings()
    history = _prior_turns(messages)
    if not settings.rag_query_rewriting or not history:
        return query

    result = await get_llm_client().chat(
        [
            {
                "role": "user",
                "content": CONTEXTUALIZE_QUERY.render(history=history, query=query),
            }
        ],
        temperature=0,
        max_tokens=128,
        operation="query_rewrite",
    )
    rewritten = (result.content or "").strip()
    if not rewritten:
        raise RuntimeError("The query-rewriting model returned an empty search query.")
    return rewritten[:1000]
