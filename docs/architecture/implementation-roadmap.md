# Cortex implementation roadmap

## Purpose and delivery principles

Cortex is a document assistant built to answer questions using authorized document evidence,
cite the evidence, and report when that evidence is insufficient. A configured LLM generates
answers; missing credentials or unavailable providers are setup or service errors, never a
reason to return a fabricated answer.

Work is delivered in small phases. Each phase should leave the application runnable,
document the concepts introduced, and add tests for the behavior changed. Existing
workspace files and working features are preserved unless a change is required by an
accepted design decision.

## Architecture baseline

```text
React/Vite browser
  ├── REST: auth, knowledge bases, documents, conversations, settings, evaluations
  └── SSE: streamed chat events and citations
             │
             ▼
FastAPI API ── request validation, auth/RBAC, rate limits, error mapping
  ├── Chat service ── prompt/context management ── LLM provider
  │      └── RAG ── authorized retrieval ── fusion/reranking ── citations
  ├── PostgreSQL ── durable users, documents, conversations, usage, evaluations
  ├── Redis ── queue, caching, rate limits
  └── arq worker ── extract → chunk → embed → index → update status
                         └── vector-store interface → Qdrant initially
```

### Boundaries and invariants

- The API owns identity, authorization, input validation, and HTTP concerns. Services
  orchestrate workflows; repositories own relational persistence.
- LLM, embedding, and vector-store providers are behind narrow interfaces so provider
  changes do not leak through the API or retrieval orchestration.
- PostgreSQL is the durable system of record. Vector indexes are derived and rebuildable.
- Ingestion is asynchronous. A document is not reported as ready until indexing succeeds;
  failures remain observable in document status.
- Every retrieval is constrained to the caller's authorized knowledge bases and
  documents. UI filtering is not a security boundary.
- Retrieved document text is untrusted data, not instructions. Grounded answers cite
  retrieved evidence and disclose insufficient context.
- Streaming must preserve explicit error events and finish/close semantics. It must not
  turn provider failures into success-shaped answer text.
- Runtime LLM calls use configured providers and environment-based credentials. Tests
  may use fakes only when the test clearly isolates provider-independent behavior.

### Technology decisions

| Concern | Baseline | Rationale and trade-off |
|---|---|---|
| Frontend | Existing React/Vite SPA | Preserve the working application and component ecosystem rather than replace it with a second UI. |
| API | FastAPI, Pydantic, SQLAlchemy | Existing async API and typed validation fit the service boundaries and Python AI ecosystem. |
| Relational data | PostgreSQL | Durable transactional source of truth for users, document metadata, conversations, and usage. |
| Queue/cache | Redis with arq | Keeps parsing and indexing out of chat requests; adds an operational dependency. |
| Vector index | Qdrant initially | Existing project choice and dedicated vector search service; keep the interface replaceable. ChromaDB is not introduced unless an explicit requirement outweighs migration cost. |
| LLM interface | Azure OpenAI and OpenAI-compatible endpoint | Supports hosted deployments and compatible gateways/local development without embedding provider details in RAG code. |
| RAG orchestration | Custom retrieval and context assembly; LangGraph where agent workflows add value | Makes retrieval behavior inspectable while retaining graph orchestration for tool-using workflows. |
| Observability | Structured logs, OpenTelemetry, metrics, usage records | Supports latency, failure, token, cost, and retrieval diagnostics while requiring sensitive-data controls. |

### Security and privacy

Authentication and role checks must be enforced server-side. Resource ownership must
be verified on reads, writes, deletes, and retrieval. Secrets belong in environment
configuration and must never be logged. Prompt and response logging must be minimized
or redacted; document contents and personal data require explicit retention and access
controls. Rate limits and provider timeouts/retries protect availability and cost, but
retries must be bounded and must not hide errors.

## Phased implementation

Each phase closes with focused tests or a documented reason they cannot run, a runnable
state check, a learning summary, interview questions, and a small exercise.

| Phase | Scope | Exit criteria |
|---|---|---|
| 1. Requirements and architecture | Confirm user journeys, system boundaries, security invariants, technology decisions, and staged scope. | Architecture baseline and this roadmap are recorded before implementation changes. |
| 2. Repository and environment | Inspect existing modules, dependencies, configuration, migration path, and local commands; fill only verified setup gaps. | Reproducible configuration/setup guidance and a baseline test/build result. |
| 3. Real LLM chat | Verify provider abstraction, configurable model and generation options, retries/timeouts, usage capture, and streaming. | A configured real provider produces streamed responses; absent/bad credentials yield explicit errors. |
| 4. Document ingestion | Verify upload validation, PDF/DOCX/TXT/Markdown extraction, metadata, deduplication, deletion/update, and worker status. | Ingestion is asynchronous and document failures are visible and recoverable. |
| 5. Chunking, embeddings, vector storage | Add or verify fixed, recursive, semantic, and structure-aware chunking; batch embeddings; vector-store boundary and re-indexing. | Tested chunking/index lifecycle and a documented embedding dimension/model constraint. |
| 6. Basic RAG | Add/verify authorized retrieval, context budgeting, grounded prompts, insufficient-context behavior, and source citations. | API response cites returned evidence and does not answer from unavailable context. |
| 7. Hybrid retrieval and reranking | Implement BM25 + vector retrieval, rank fusion, metadata filtering, reranking, and diagnostics. | Retrieval tests cover lexical, semantic, filtered, and fused results. |
| 8. Chat UI and streaming | Connect chat, upload, document status, citations, history, and error/loading states to actual API behavior. | Browser flow works against the API, including partial streamed output and failure states. |
| 9. Conversation and advanced RAG | Add conversation-aware follow-ups and independently testable query transformation, compression, parent-child, multi-step, or optional agentic retrieval. | Each enabled strategy has a clear config/use case, tests, and measured comparison; no unverified claims. |
| 10. Production capabilities | Harden auth/RBAC, limits, retries, structured errors, logging redaction, worker recovery, and operational configuration. | Security and failure-path checks pass; documented deployment assumptions are explicit. |
| 11. Evaluation and observability | Add evaluation datasets and retrieval/answer metrics, latency, usage/cost tracking, and debugging views. | Evaluation results come from actual runs and state dataset/provider conditions. |
| 12. Deployment and documentation | Validate Docker Compose and setup/run/test instructions; document operations and known limitations. | A clean deployment path and smoke checks are documented. |
| 13. Interview preparation | Create project defense and substantial topic-organized questions tied to implemented concepts. | Answers are technically grounded in this repository and avoid repetitive filler. |

## Scope management

The initial delivery prioritizes a working, secure end-to-end path: real LLM chat,
asynchronous document ingestion, authorized retrieval, citations, and visible failures.
GraphRAG, agentic retrieval, Ragas/DeepEval integrations, and advanced UI dashboards
are added only after the core flow is tested and the added complexity has a measurable
purpose. Evaluation scores are never fabricated.

The current baseline uses Qdrant and React/Vite. Both are intentional continuity choices
for this existing workspace, not claims that ChromaDB or plain JavaScript are unsuitable.
Changing either requires an explicit migration decision and validation of the existing
application.
