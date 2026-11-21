# ADR-0001: PostgreSQL as system of record + Qdrant for vectors

**Status:** Accepted

## Context
We need durable relational data (users, documents, conversations, costs) and fast
approximate-nearest-neighbor search over ~millions of embedding vectors.

## Decision
PostgreSQL for all relational data. Qdrant as a dedicated vector database.
Chunk text is duplicated into Qdrant payloads to avoid joins on the search hot path.

## Alternatives considered
- **pgvector**: one fewer service, transactional consistency with metadata. Rejected here to
  demonstrate a dedicated vector DB and because Qdrant offers better ANN performance/filtering
  at scale (HNSW tuning, payload indexes, horizontal sharding).
- **Pinecone/Weaviate**: managed/heavier; Qdrant is open-source, self-hostable, simple ops.

## Consequences
- Two stores to operate; eventual consistency between chunk rows and vectors.
- Qdrant is treated as a rebuildable index — losing it is recoverable by re-embedding.
- Deletion must fan out to both stores (see DocumentService.delete_document).
