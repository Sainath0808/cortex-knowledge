# Cortex — Architecture Overview

## System components

| Component | Technology | Responsibility |
|---|---|---|
| API | FastAPI (async) | Auth, rate limiting, request orchestration |
| Agent | LangGraph | Reason/act loop: decides when to search, calculate, answer |
| RAG pipeline | Custom (ai/rag) | Retrieve → rerank → context build → grounded generation |
| Vector store | Qdrant | Dense vector search over document chunks |
| System of record | PostgreSQL | Users, documents, chunks, conversations, costs, evals |
| Cache / queue / rate limit | Redis | arq job queue, sliding-window rate limiting |
| Worker | arq | Async ingestion: chunk → embed → index |
| LLM provider | Azure OpenAI | gpt-4o (chat/agent/judge), text-embedding-3-large |
| MCP server | mcp (FastMCP) | Standardized tool access to the knowledge base |
| Observability | OTel + structlog + Prometheus | Traces, JSON logs, metrics, cost records |

## Request flow: one chat turn

1. `POST /api/v1/chat` — middleware assigns request_id, checks rate limit.
2. JWT decoded → user loaded → RBAC applies.
3. `ChatService.chat` or `ChatService.stream`:
   - Guardrails: injection heuristics + LLM classifier; PII redaction.
   - Conversation loaded (ownership enforced); history trimmed to token budget.
   - LangGraph agent runs: guard → streaming agent (LLM w/ tools) ⇄ tools → final answer.
   - `knowledge_search` tool → user- and knowledge-base-scoped hybrid retriever (Qdrant + PostgreSQL BM25)
     → fused context returned to agent.
   - Output moderation, persistence (messages + citations), response.
   - `/chat/stream` forwards real model token chunks as SSE and emits citations on completion.
4. LLM calls and request flow are traced via OTel; configured usage records are stored in
   `llm_usage`.

## Ingestion flow

1. `POST /documents/upload` — text and supported metadata extracted (pypdf/python-docx/bs4);
   exact extracted content is deduplicated per owner and knowledge base, then the Document row
   is created (`pending`) in the selected knowledge base.
2. Job enqueued to Redis (arq).
3. Worker: chunk (token-aware, overlapping) → store chunk rows → embed (batched)
   → upsert vectors+payloads to Qdrant → mark `ready` (or `failed` with error).
4. UI polls document status.

## Why vectors in Qdrant but text in Postgres?

Postgres is the durable system of record (transactions, migrations, backups); Qdrant is a
rebuildable index optimized for ANN search. If Qdrant is lost, re-embed from Postgres.
Payloads in Qdrant duplicate chunk text so the hot search path needs no join.

## Failure handling

- LLM failures: tenacity retries w/ exponential backoff on 429/timeouts/connection errors,
  then `502 UpstreamAIError` — never a hang, never silent.
- Redis down: rate limiter fails open (availability > throttling).
- Worker failure: document marked `failed` with error; arq retries transient errors (max 3).
- Agent runaway: hard tool-call budget (6) terminates loops.

## Scaling path

- API and workers scale horizontally (stateless; HPA included).
- Postgres: read replicas for conversation history; partition `llm_usage` by month.
- Qdrant: sharded collections / Qdrant cluster.
- Cost control: per-request usage records enable per-user budgets; cheap model (gpt-4o-mini)
  for classification/rerank paths is a config change.
