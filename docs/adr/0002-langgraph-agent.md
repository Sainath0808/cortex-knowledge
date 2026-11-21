# ADR-0002: LangGraph for the agent runtime

**Status:** Accepted

## Context
The chat experience needs an agent that can decide between answering directly and calling
tools (knowledge search, calculator, stats), with guardrails and loop protection.

## Decision
A hand-built LangGraph `StateGraph`: guard → agent ⇄ tools, with typed state,
conditional routing, and a hard tool-call budget. We deliberately did NOT use
`create_react_agent` so every node and edge is explicit and explainable.

## Alternatives considered
- **Raw OpenAI tool-calling loop**: simpler, but no graph structure for adding
  human-in-the-loop interrupts, checkpointing, or multi-agent topologies later.
- **AutoGen/CrewAI**: multi-agent frameworks are overkill for a single-agent product surface.
- **LangChain AgentExecutor (legacy)**: superseded by LangGraph.

## Consequences
- State is a typed dict with an append-only messages reducer — easy to test nodes in isolation.
- Adding durability = swapping in LangGraph's Postgres checkpointer (documented future work).
- Two LLM client paths exist (our LLMClient for RAG, langchain-openai for the agent);
  acceptable trade-off for LangGraph's native tool binding.
