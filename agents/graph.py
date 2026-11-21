"""LangGraph agent: a hand-built ReAct loop with guardrails and a step budget.

Graph topology:

    START -> guard -> agent <-> tools
                        |
                        v
                       END

- guard: prompt-injection check; blocks before any LLM/tool spend.
- agent: LLM with bound tools decides to answer or call tools.
- tools: executes requested tool calls, results feed back to agent.
- A hard tool-call budget prevents infinite agent loops.
"""

import time
from functools import lru_cache
from uuid import UUID

import structlog
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.telemetry import get_tracer
from langchain_core.messages import AIMessage, SystemMessage
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from agents.state import AgentState
from agents.tools import ALL_TOOLS
from ai.guardrails.injection import check_input
from ai.llm.costs import estimate_cost
from ai.llm.prompts import AGENT_SYSTEM

logger = get_logger(__name__)

MAX_TOOL_CALLS = 6


@lru_cache
def _get_model():
    """Provider seam (mirrors ai/llm/client.py): azure or any OpenAI-compatible endpoint."""
    s = get_settings()
    if s.llm_provider == "azure":
        model = AzureChatOpenAI(
            azure_endpoint=s.azure_openai_endpoint,
            api_key=s.azure_openai_api_key,
            api_version=s.azure_openai_api_version,
            azure_deployment=s.azure_openai_chat_deployment,
            temperature=s.llm_temperature,
            max_completion_tokens=s.llm_max_completion_tokens,
            timeout=s.llm_timeout_seconds,
            max_retries=2,
            streaming=True,
            stream_usage=True,
        )
    else:
        model = ChatOpenAI(
            base_url=s.llm_base_url or None,
            api_key=s.llm_api_key,
            model=s.llm_chat_model,
            temperature=s.llm_temperature,
            max_completion_tokens=s.llm_max_completion_tokens,
            timeout=s.llm_timeout_seconds,
            max_retries=2,
            streaming=True,
            stream_usage=True,
        )
    return model.bind_tools(ALL_TOOLS)


async def guard_node(state: AgentState) -> dict:
    """Block prompt-injection attempts before spending agent/LLM budget."""
    last_user = state["messages"][-1].content
    verdict = await check_input(str(last_user), use_classifier=False)
    if verdict.blocked:
        message = "I can't process that request — it was flagged by our safety guardrails."
        return {
            "guardrail_blocked": True,
            "messages": [AIMessage(content=message)],
        }
    return {"guardrail_blocked": False}


async def agent_node(state: AgentState) -> dict:
    with get_tracer().start_as_current_span("agent.reason") as span:
        messages = [SystemMessage(content=AGENT_SYSTEM.template), *state["messages"]]
        response_chunk = None
        started_at = time.perf_counter()
        async for chunk in _get_model().astream(messages):
            response_chunk = chunk if response_chunk is None else response_chunk + chunk
        if response_chunk is None:
            raise RuntimeError("The LLM provider returned no response.")
        usage = response_chunk.usage_metadata or {}
        prompt_tokens = usage.get("input_tokens", 0)
        completion_tokens = usage.get("output_tokens", 0)
        if prompt_tokens or completion_tokens:
            settings = get_settings()
            model_name = (
                settings.azure_openai_chat_deployment
                if settings.llm_provider == "azure"
                else settings.llm_chat_model
            )
            context = structlog.contextvars.get_contextvars()
            try:
                from app.db.repositories.usage import record_usage

                await record_usage(
                    operation="agent_chat",
                    model=model_name,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost_usd=estimate_cost(model_name, prompt_tokens, completion_tokens),
                    latency_ms=(time.perf_counter() - started_at) * 1000,
                    request_id=context.get("request_id"),
                    user_id=(UUID(context["user_id"]) if context.get("user_id") else None),
                )
            except Exception:
                logger.exception("agent_usage_record_failed")
        response = AIMessage(
            content=response_chunk.content,
            additional_kwargs=response_chunk.additional_kwargs,
            response_metadata=response_chunk.response_metadata,
            tool_calls=response_chunk.tool_calls,
            invalid_tool_calls=response_chunk.invalid_tool_calls,
            id=response_chunk.id,
            usage_metadata=response_chunk.usage_metadata,
        )
        tool_calls = getattr(response, "tool_calls", []) or []
        span.set_attribute("agent.tool_calls", len(tool_calls))

        if tool_calls and state.get("tool_call_count", 0) + len(tool_calls) > MAX_TOOL_CALLS:
            logger.warning("agent_tool_budget_exceeded")
            return {
                "messages": [
                    AIMessage(
                        content=(
                            "I hit my tool-use limit for this request. "
                            "Here is what I found so far: "
                        )
                        + (response.content or "no conclusive answer yet.")
                    )
                ]
            }
        return {
            "messages": [response],
            "tool_call_count": state.get("tool_call_count", 0) + len(tool_calls),
        }


def route_after_guard(state: AgentState) -> str:
    return END if state.get("guardrail_blocked") else "agent"


def route_after_agent(state: AgentState) -> str:
    last = state["messages"][-1]
    if getattr(last, "tool_calls", None):
        return "tools"
    return END


def build_graph():
    graph = StateGraph(AgentState)
    graph.add_node("guard", guard_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(ALL_TOOLS))

    graph.add_edge(START, "guard")
    graph.add_conditional_edges("guard", route_after_guard, {"agent": "agent", END: END})
    graph.add_conditional_edges("agent", route_after_agent, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()


@lru_cache
def get_agent():
    return build_graph()
