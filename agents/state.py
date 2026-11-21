"""Agent state: the shared, typed state that flows through the LangGraph graph."""
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    # add_messages is a reducer: node outputs append instead of overwrite.
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    knowledge_base_id: str | None
    citations: list[dict]
    guardrail_blocked: bool
    tool_call_count: int
