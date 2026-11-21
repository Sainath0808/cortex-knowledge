# Hybrid retrieval and tenant isolation

## What and why

Dense vector search finds semantically similar passages even when query and document
vocabulary differ. BM25 finds exact terms and rare keywords such as product names, error
codes, policy labels, and identifiers. Hybrid retrieval runs both and combines ranked lists
with Reciprocal Rank Fusion (RRF), avoiding direct comparison of differently scaled scores.

## Flow

```text
authenticated user + query
  → contextualize follow-up using prior conversation (when enabled)
  → embed query
  ├── Qdrant dense search filtered by owner_id
  └── PostgreSQL BM25 over that owner's chunks
  → RRF merge → rerank → context selection → grounded answer
```

`owner_id` is required at the retrieval boundary. The API supplies the authenticated
identity; the LangGraph tool receives it through injected graph state; MCP and evaluation
use separately configured service-account IDs. Both vector and lexical paths apply the
same owner restriction. New Qdrant points carry `owner_id`; the one-time
`scripts/backfill_vector_owners.py` command updates pre-existing payloads.

The BM25 implementation uses Okapi term frequency, inverse document frequency, and document
length normalization over at most 10,000 rows for the selected owner. RRF assigns each
result a reciprocal-rank contribution (`1 / (k + rank)`) and sums contributions for a
chunk present in both lists.

## Trade-offs and limits

- Dense search is robust to paraphrase but may miss exact identifiers.
- BM25 is explainable and exact-term-sensitive, but it does not understand synonyms.
- RRF avoids score calibration and is robust to one weak list, but adds a fusion parameter
  and does not use original score magnitudes.
- Follow-up query rewriting resolves references using the preceding conversation. It is
  configurable with `RAG_QUERY_REWRITING`; the owner and knowledge-base filters remain
  injected by the application and are never part of model-generated search arguments.
- Loading up to 10,000 authorized chunks per query is suitable for a learning/demo corpus,
  not a high-throughput large tenant. Move BM25 to PostgreSQL full-text search, an inverted
  index service, or a dedicated search cluster at scale.
- Existing Qdrant points without owner metadata are intentionally invisible to scoped
  vector search until backfilled. Do not remove the owner filter as a compatibility
  workaround.

## Implementation and verification

`ai/rag/query_rewrite.py` contextualizes agent follow-up searches;
`ai/rag/bm25.py` tokenizes and ranks the authorized lexical corpus;
`ai/rag/retriever.py` runs dense and lexical retrieval concurrently and fuses results;
`ai/rag/vectorstore.py` applies Qdrant payload filters; and the API/agent pass the
authenticated owner ID. `MCP_OWNER_ID` and `EVAL_OWNER_ID` are mandatory for their
respective non-interactive workflows.

```powershell
python scripts/backfill_vector_owners.py
python -m pytest -q tests\test_rag_pipeline.py
```

The backfill command requires PostgreSQL and Qdrant to be available. It updates payload
metadata only; it does not re-embed documents.

## Failure modes

- Missing service-account IDs stop MCP/evaluation retrieval instead of performing global
  search.
- Dense or lexical provider/database failures are surfaced; there is no cross-tenant
  fallback.
- A user with more than 10,000 chunks has a bounded BM25 candidate corpus; monitor recall
  and migrate lexical search before this cap affects evaluation.

## Interview questions

1. **Why combine BM25 and vectors?** Their failure modes differ: BM25 covers exact terms;
   vectors cover paraphrases. Fusion often improves recall over either alone.
2. **Why RRF instead of summing scores?** Vector similarity and BM25 scores are not
   calibrated to the same scale. RRF uses order rather than incompatible magnitudes.
3. **Where should tenant filtering happen?** In each retrieval backend before results are
   returned. Filtering after retrieval risks exposing unauthorized text to the model.
4. **How would you scale lexical retrieval?** Use PostgreSQL full-text indexes or a search
   system with inverted indexes, retain owner filters at query time, then compare metrics
   against the current BM25 baseline.
5. **What does query rewriting change, and what must it never change?** It may resolve
   references in a follow-up question to improve recall. It must not choose the user identity
   or knowledge-base scope; those authorization filters remain application-controlled.
