"""Agent unit tests: routing logic, tool safety, budget enforcement."""

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langgraph.graph import END

from agents.graph import MAX_TOOL_CALLS, build_graph, route_after_agent, route_after_guard
from agents.tools import calculator, knowledge_search


class TestRouting:
    def test_guard_blocks_routes_to_end(self):
        state = {"messages": [], "guardrail_blocked": True, "citations": [], "tool_call_count": 0}
        assert route_after_guard(state) == END

    def test_guard_pass_routes_to_agent(self):
        state = {"messages": [], "guardrail_blocked": False, "citations": [], "tool_call_count": 0}
        assert route_after_guard(state) == "agent"

    def test_agent_with_tool_calls_routes_to_tools(self):
        msg = AIMessage(
            content="",
            tool_calls=[{"name": "calculator", "args": {"expression": "1+1"}, "id": "t1"}],
        )
        state = {
            "messages": [HumanMessage(content="hi"), msg],
            "guardrail_blocked": False,
            "citations": [],
            "tool_call_count": 0,
        }
        assert route_after_agent(state) == "tools"

    def test_agent_final_answer_routes_to_end(self):
        state = {
            "messages": [AIMessage(content="Done.")],
            "guardrail_blocked": False,
            "citations": [],
            "tool_call_count": 0,
        }
        assert route_after_agent(state) == END


class TestCalculatorTool:
    def test_basic_math(self):
        assert calculator.invoke({"expression": "(2 + 3) * 4"}) == "20"

    def test_rejects_code_execution(self):
        result = calculator.invoke({"expression": "__import__('os').system('dir')"})
        assert "Could not evaluate" in result

    def test_rejects_names(self):
        result = calculator.invoke({"expression": "open('secrets.txt')"})
        assert "Could not evaluate" in result


def test_tool_budget_constant_is_sane():
    assert 1 <= MAX_TOOL_CALLS <= 20


def test_knowledge_search_hides_injected_owner_from_model_schema():
    assert set(knowledge_search.tool_call_schema.model_fields) == {"query"}


async def test_agent_graph_streams_model_tokens(monkeypatch):
    class StreamingModel:
        async def astream(self, messages):
            yield AIMessageChunk(content="Hello ")
            yield AIMessageChunk(content="world.")

    monkeypatch.setattr("agents.graph._get_model", lambda: StreamingModel())
    graph = build_graph()
    tokens = []
    final_state = None
    async for mode, data in graph.astream(
        {
            "messages": [HumanMessage(content="Say hello.")],
            "citations": [],
            "guardrail_blocked": False,
            "tool_call_count": 0,
        },
        stream_mode=["messages", "values"],
    ):
        if mode == "messages":
            chunk, metadata = data
            if metadata.get("langgraph_node") == "agent":
                tokens.append(chunk.content)
        elif mode == "values":
            final_state = data

    assert "".join(tokens) == "Hello world."
    assert final_state["messages"][-1].content == "Hello world."
