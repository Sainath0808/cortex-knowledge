# Cortex Interview and Project Defense Guide

Use this guide to explain the project clearly, demonstrate the architecture, and discuss
engineering trade-offs honestly. Be precise about what has been implemented versus what
still needs a live end-to-end verification.

## 30-second introduction

> Cortex is an enterprise knowledge assistant that ingests documents asynchronously and
> answers questions with citations. It combines a FastAPI service, a LangGraph tool-using
> agent, hybrid dense-and-keyword retrieval, and user-scoped knowledge bases. PostgreSQL is
> the source of truth, Qdrant stores searchable vectors, and Redis/arq handles background
> ingestion. The project emphasizes traceable answers, explicit tenant boundaries, and
> observable failures rather than presenting an LLM response as automatically trustworthy.

## Two-minute project walkthrough

1. **Problem:** Organizational policies and reference material are difficult to search;
   general chat models can invent answers or miss exact terms.
2. **Upload:** The API extracts text and metadata, checks the owner's content hash, saves a
   pending document, and queues ingestion.
3. **Index:** The worker chunks the document, stores canonical chunk text in PostgreSQL,
   embeds the chunks, writes vectors and owner/scope metadata to Qdrant, and updates status.
4. **Ask:** The API authenticates the user and loads the conversation. The LangGraph agent
   chooses whether to call `knowledge_search`; follow-up queries can be rewritten as
   standalone search queries.
5. **Retrieve:** Dense Qdrant search and PostgreSQL BM25 use the same owner and selected
   knowledge-base filters. Reciprocal Rank Fusion merges the ranked lists; an LLM reranker
   selects context for grounded generation.
6. **Respond:** The model streams tokens over SSE. Moderation is applied, citations are
   persisted, and usage/latency/cost are recorded when available.

## Architecture at a glance

| Layer | Implementation | Responsibility |
|---|---|---|
| Web client | React + Vite | Chat, document lifecycle, knowledge-base management, settings, admin dashboard |
| API | FastAPI, async SQLAlchemy | Authentication, authorization, request validation, streaming |
| Agent | LangGraph | Guard → model/tool decision → tools → final answer |
| Retrieval | Dense + BM25 + RRF + reranking | Find and rank evidence under user-controlled scope |
| Relational store | PostgreSQL | Users, documents, chunks, conversations, usage, evaluations |
| Vector index | Qdrant | Approximate nearest-neighbor search and retrieval payloads |
| Queue/cache | Redis + arq | Asynchronous ingestion and rate limiting |
| Telemetry | OpenTelemetry + structured logs | Request traces and operational diagnostics |

## Common interview questions

### Why build RAG instead of fine-tuning?

RAG lets the application retrieve current, permission-scoped evidence at request time and
show its sources. Fine-tuning is more appropriate for learning behavior or formats than
for frequently changing private facts. RAG also lets document updates happen without
retraining a model.

### Why combine vector search and BM25?

Dense retrieval finds semantically related passages when wording differs. BM25 is useful
for exact names, identifiers, error codes, and policy terms. Their score scales are
different, so Cortex fuses their ranks with Reciprocal Rank Fusion rather than adding raw
scores.

### Why is PostgreSQL paired with Qdrant?

PostgreSQL provides transactions and a durable source of truth for users, documents, chunk
text, and conversations. Qdrant is optimized for vector similarity search and can be
rebuilt from canonical data. The trade-off is that indexing updates two stores and needs
failure handling and reconciliation.

### How do you prevent cross-user retrieval?

The authenticated application supplies the owner ID; the model cannot choose it. Both
Qdrant and BM25 filter by owner before returning results. Knowledge-base scope is validated
against ownership and is persisted with the conversation. A knowledge-base UUID alone is
never treated as authorization.

### How are answers grounded?

The retrieval prompt instructs the model to answer from supplied context and say when the
evidence is insufficient. Context blocks carry chunk IDs and document titles, which can be
used for citations. These controls improve verifiability but do not mathematically
guarantee that every generated claim is supported.

### What does the LangGraph agent add over a fixed RAG chain?

A fixed RAG chain always searches and generates. The agent can choose among tools, such as
searching documents or using a calculator, and can call tools more than once. The graph
adds a tool-call budget and a guard node to bound runaway behavior and reject flagged
inputs before tool execution.

### Why use asynchronous ingestion?

Parsing, chunking, embedding, and indexing can take much longer than an HTTP request should
remain open. The API returns a document status while an arq worker processes a Redis job.
The UI can then show `pending`, `processing`, `ready`, or `failed`, including an error
message when ingestion fails.

### How are follow-up questions handled?

An optional contextualizer uses recent user and assistant messages to resolve references
such as “what about the second policy?” into a standalone search query. This can improve
retrieval, but it does not determine the owner or knowledge-base filters; those stay
application-controlled. The feature can be disabled through `RAG_QUERY_REWRITING`.

### How do you handle prompt injection?

The system layers heuristic checks, an optional classifier, prompts that treat retrieved
content as untrusted data, and output moderation. No single layer is sufficient, and a
classifier or regex can miss attacks. I would describe this as risk reduction, not a
security proof.

### What are the main trade-offs or current limits?

- BM25 currently loads a bounded corpus of up to 10,000 authorized chunks per query; a
  larger deployment should use indexed full-text search or a dedicated lexical service.
- Query rewriting and LLM reranking add latency and model cost.
- PostgreSQL and Qdrant do not share a transaction; document moves restore the prior vector
  scope if the relational commit fails, while a transactional outbox would be stronger
  under process crashes.
- Knowledge bases are user-owned; team sharing and membership-based ACLs are not included.
- Cost values are estimates, not provider invoices.
- A production claim requires live deployment, operational monitoring, and measured
  retrieval/answer quality, not just a successful build.

### How would you measure retrieval and answer quality?

Use a representative, held-out set of questions with relevant chunk labels. Compare
dense-only, BM25-only, and hybrid retrieval with hit rate, precision/recall at k, and MRR.
For generated answers, measure citation support and faithfulness, combine automated
signals with human review, and track latency and cost. Treat LLM-judge scores as regression
signals rather than absolute truth.

## Design and operational follow-ups

Be ready to sketch or explain:

- **A document move:** verify caller ownership and destination ownership; check destination
  hash uniqueness; update PostgreSQL membership and Qdrant payload scope; define what
  happens if either write fails.
- **A tenant boundary test:** create two users with similarly named documents and prove
  that neither lexical nor vector results cross the owner filter.
- **A provider outage:** bounded retries, explicit upstream errors, visible ingestion
  failures, and traces that identify which dependency failed.
- **Scaling lexical search:** replace per-query corpus loading with PostgreSQL full-text
  indexes or a search service while retaining authorization filters in the query.
- **Scaling ingestion:** make jobs idempotent, constrain concurrency, track retries, and
  reconcile documents whose database and vector-index states diverge.
- **A team-sharing requirement:** model workspace membership and roles explicitly, then
  derive the authorized owner/workspace filter from server-side identity.

## Suggested live demo

1. Sign in and create a knowledge base for a clearly named topic.
2. Upload a small policy or reference document and show its ingestion status changing to
   `ready`.
3. Ask a question whose answer appears in the document; show the streamed answer and
   citation.
4. Ask a follow-up that uses a reference such as “what about the exception?” and explain
   how query contextualization helps retrieval.
5. Move the ready document to another knowledge base and show that the selected scope
   changes.
6. Open Settings to show provider/retrieval configuration, then the admin dashboard to
   show usage and evaluation history if available.

Do not claim a live demo succeeded unless the API, database, Redis, Qdrant, worker, and
configured model provider are actually running.

## Resume bullets (adapt to measured results)

- Built an async document-ingestion and RAG application with FastAPI, React, LangGraph,
  PostgreSQL, Redis/arq, and Qdrant.
- Implemented owner-scoped hybrid retrieval using dense vectors, BM25, reciprocal-rank
  fusion, reranking, and cited answer generation.
- Added streamed chat, configurable follow-up query rewriting, document lifecycle
  controls, and user-owned knowledge-base scopes.
- Instrumented model operations and added usage/evaluation views for cost, latency, and
  retrieval-quality iteration.

Add scale, accuracy, latency, or cost numbers only after measuring them on a representative
corpus and recording the evaluation setup.

## Project reference docs

- [Architecture overview](architecture/overview.md)
- [Agent design](ai/agents.md)
- [RAG design](ai/rag-design.md)
- [Hybrid retrieval](ai/hybrid-search.md)
- [Guardrails and security](ai/security.md)
- [Evaluation strategy](ai/evals.md)
