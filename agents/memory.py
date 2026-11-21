"""Conversation memory: reconstructs agent message history from Postgres.

Short-term memory = the conversation's message history, trimmed to a token
budget (most recent first). Long-term memory = the knowledge base itself,
accessed through retrieval rather than stuffed into the prompt.
"""
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from ai.rag.chunking import count_tokens
from app.db.models import Conversation

HISTORY_TOKEN_BUDGET = 3000


def build_history(conversation: Conversation | None) -> list[BaseMessage]:
    """Convert persisted messages to LangChain messages, newest-first trim."""
    if conversation is None:
        return []
    selected: list[BaseMessage] = []
    used = 0
    for msg in reversed(conversation.messages):
        if msg.role == "tool":
            continue  # tool transcripts are not replayed across turns
        tokens = count_tokens(msg.content)
        if used + tokens > HISTORY_TOKEN_BUDGET:
            break
        cls = HumanMessage if msg.role == "user" else AIMessage
        selected.insert(0, cls(content=msg.content))
        used += tokens
    return selected
