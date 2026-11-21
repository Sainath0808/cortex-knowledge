# ADR-0003: Async ingestion via arq worker

**Status:** Accepted

## Context
Ingesting a document = parse → chunk → embed (network calls) → index. A 100-page PDF can take
minutes. HTTP handlers cannot block that long.

## Decision
API creates the Document row (`pending`), enqueues a job to Redis via arq, returns 202.
A separate worker process consumes jobs: chunk → persist chunks → embed batched → upsert
Qdrant → mark `ready`/`failed`. Clients poll status.

## Alternatives considered
- **FastAPI BackgroundTasks**: runs in the API process — lost on restart/deploy, no retries,
  competes with request latency.
- **Celery**: heavier; arq is async-native and matches our asyncio stack.
- **Kafka**: unjustified operational cost at this scale.

## Consequences
- Status lifecycle (`pending → processing → ready|failed`) is part of the API contract.
- Worker scales independently of the API (separate K8s deployment).
- At-least-once execution: ingestion steps are idempotent (upsert semantics in Qdrant).
