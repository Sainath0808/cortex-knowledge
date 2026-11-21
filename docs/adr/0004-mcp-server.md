# ADR-0004: MCP server for external tool access

**Status:** Accepted

## Context
The knowledge base is valuable beyond our own UI: other agents, IDEs, and assistants should be
able to search it without bespoke integrations.

## Decision
Expose retrieval as a Model Context Protocol server (`mcp_server/`), reusing the exact same
`ai/rag` retrieval code as the in-process agent. Tools: `knowledge_search`, `list_documents`;
resource: `cortex://stats`. stdio transport by default.

## Alternatives considered
- **Plain REST only**: every client needs custom glue; MCP clients get tool discovery,
  schemas, and invocation for free.
- **OpenAPI plugin specs**: fragmented, assistant-specific; MCP is the emerging standard.

## Consequences
- One retrieval implementation, two transports (in-process tool + MCP) — no drift.
- MCP server runs with read-only DB access in production; auth/tenancy for remote (SSE)
  transport is future work.
