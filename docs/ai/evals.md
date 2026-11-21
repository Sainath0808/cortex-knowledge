# Evaluation Strategy

"If you can't measure it, you can't improve it" applies doubly to RAG: chunking, top_k,
reranking, prompts, and models all interact. Evals turn tuning from vibes into engineering.

## Golden dataset (ai/evals/datasets/golden.jsonl)
Query → relevant documents (+ expected answer keywords). Small by design — start with 20–50
high-quality cases from real user questions; grow from production failures.

## Retrieval metrics (ai/evals/retrieval_metrics.py)
- **precision@k** — how much of what we retrieved is relevant (context quality).
- **recall@k** — how much of what's relevant we retrieved (missed evidence).
- **MRR** — how high the first relevant hit ranks (matters because context is packed
  most-relevant-first).
- **hit_rate@k** — did we get at least one relevant chunk (floor metric).

## Generation metrics (ai/evals/llm_judge.py)
LLM-as-judge **faithfulness** (1–5): are the answer's claims supported by the retrieved
context? Judge scores are noisy — use them as *regression signals across versions* (prompt v1
vs v2, chunk 512 vs 256), not absolute truth. Temperature 0, JSON-forced output.

## Workflow
```
python -m ai.evals.run_evals             # full run
python -m ai.evals.run_evals --skip-generation   # fast retrieval-only
```
Each run is stored in the `eval_runs` table (metrics + dataset size) and visible at
`GET /api/v1/admin/evals` — trends over time, tied to prompt versions in `ai/llm/prompts.py`.
The admin Dashboard also shows recent run metrics and estimated LLM calls, tokens, cost,
and latency. Usage can be filtered to 7, 30, or 90 days and is grouped by operation/model.
Costs are estimates based on the configured model price table, not provider invoices.

## What triggers an eval run
- Any change to chunking parameters, embedding model, retrieval top_k, rerank strategy,
  or the RAG/agent prompts (all versioned).
- CI can run retrieval evals against a seeded test index (generation evals cost money —
  run on demand / nightly).
