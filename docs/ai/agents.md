# Agent Architecture

## What makes this an agent (vs a workflow)
The RAG pipeline is a *workflow*: fixed steps, deterministic control flow. The agent adds a
decision loop: the LLM inspects the conversation and *chooses* whether to answer directly,
search the knowledge base, calculate, or fetch stats — possibly multiple times.

## Graph (agents/graph.py)
```
START → guard → agent ⇄ tools → END
```
- **guard**: injection heuristics before any spend. Blocked → canned refusal → END.
- **agent**: gpt-4o with bound tools. Emits either tool_calls (→ tools) or a final answer (→ END).
- **tools**: LangGraph ToolNode executes calls; results append to state; control returns to agent.
- **Budget**: hard cap of 6 tool calls per turn prevents infinite loops (a real failure mode
  when tools return unhelpful results and the model retries forever).

## State (agents/state.py)
Typed dict; `messages` uses the `add_messages` reducer (append, not overwrite) — this is how
LangGraph nodes communicate without sharing mutable objects.

## Tools (agents/tools.py)
Design rules applied:
- Docstrings are the tool's UI for the model — they say *when* to use it, not just what it does.
- Tools always return strings, including error strings the model can react to.
- `calculator` uses an AST-walking evaluator — never `eval()` (code-injection surface).
- `knowledge_search` reuses the RAG retriever and passes citations out-of-band to the service
  layer (`pop_citations`), because tool outputs go to the LLM, not to the API response.

## Memory (agents/memory.py)
- Short-term: persisted conversation messages, replayed newest-first under a 3000-token budget.
- Long-term: the knowledge base itself — retrieved on demand, never stuffed into the prompt.
- Tool transcripts are not replayed across turns (cost/noise).

## Failure handling
- LLM errors: langchain-openai retries (2), then the API's 502 path.
- Tool errors: returned as text; the model can retry differently or apologize.
- Injection: guard node + system prompt rule that retrieved text is untrusted data.

## Future: human-in-the-loop
LangGraph `interrupt` before any destructive tool (none exist today) + Postgres checkpointer
so approval can resume the graph later.
