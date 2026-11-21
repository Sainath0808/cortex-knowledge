# Chunking strategies

## What and why

Chunking converts a document into bounded passages that can be embedded and retrieved.
Chunk size controls a trade-off: small chunks improve focus but can lose surrounding
meaning; large chunks preserve context but can dilute embeddings and consume the prompt
budget. Overlap helps answers that span neighboring chunks remain retrievable.

Set `CHUNKING_STRATEGY` in `.env` to select the ingestion strategy:

| Strategy | Behavior | Strength | Cost / limitation |
|---|---|---|---|
| `fixed` | Exact token windows with token overlap. | Predictable size and simple baseline. | Can split sentences, tables, and sections. |
| `recursive` | Greedily packs paragraphs and sentences, falling back to token windows. | Good general-purpose prose default. | Does not understand document headings or topic changes. |
| `structure_aware` | Splits Markdown by headings and repeats each heading as context in its chunks. | Preserves section meaning for documentation and handbooks. | Only Markdown heading syntax is recognized; PDF layout may already be lost at extraction. |
| `semantic` | Embeds adjacent sentences and starts a new group when cosine similarity falls below a threshold; then enforces the token budget. | Can keep topic-coherent passages together. | Adds embedding calls and latency; similarity thresholds are corpus/model dependent. |

The configured defaults remain 512 tokens with 64 tokens of overlap. These are starting
values, not universal optima. Evaluate retrieval precision/recall on representative
questions before changing a production corpus; changing strategy requires re-indexing.

## Data flow and implementation

```text
arq ingest_document
  → chunk_document(strategy from settings)
      ├── fixed: token windows
      ├── recursive: paragraph → sentence → token fallback
      ├── structure_aware: Markdown sections → recursive chunks with heading context
      └── semantic: sentence embeddings → cosine boundaries → token-bounded chunks
  → persist chunk rows → embed final chunks → upsert Qdrant vectors
```

`ai/rag/chunking.py` implements the strategies and enforces token/overlap constraints.
`backend/app/core/config.py` validates the configured strategy. Semantic chunking uses the
same configured embedding provider as indexing and retrieval, keeping all vectors in one
embedding space.

## Run and verify

Choose one strategy in `.env`, restart the worker, then upload a document. The worker
applies that strategy to newly ingested documents. Existing documents are not silently
re-chunked; delete and re-ingest them when comparing strategies.

Focused checks:

```powershell
python -m pytest -q tests\test_chunking.py
```

## Failure modes

- Unknown strategy or invalid token/overlap settings fail explicitly rather than silently
  switching to another algorithm.
- Semantic embedding failures fail the ingestion job and leave the document in `failed`
  state; the worker does not invent vectors or quietly use recursive chunking.
- A new strategy changes vector content and requires re-indexing before retrieval can
  reflect the change.

## Interview questions

1. **Why not maximize chunk size?** Large passages can blur embedding relevance and occupy
   the context window. The best size depends on the corpus and retrieval evaluation.
2. **When is semantic chunking worthwhile?** When topic boundaries are not aligned with
   paragraph/heading boundaries and evaluation shows improved retrieval enough to justify
   embedding cost during ingestion.
3. **Why repeat headings in chunks?** The heading provides local context to the embedding
   and to the final answer even when only a mid-section chunk is retrieved.
4. **How do you compare strategies?** Re-index the same corpus and compare retrieval
   recall/precision and answer faithfulness on the same held-out evaluation questions.

## Exercise

Add a structure-aware parser for DOCX heading styles, preserve heading paths in chunk
metadata, and compare its retrieval metrics against recursive chunking on the same corpus.
