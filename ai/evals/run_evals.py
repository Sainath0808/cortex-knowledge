"""Eval runner: measures retrieval metrics and generation faithfulness
against the golden dataset, prints a report, and stores an EvalRun row.

Usage: python -m ai.evals.run_evals [--skip-generation]
"""
import argparse
import asyncio
import json
from pathlib import Path
from uuid import UUID

from ai.evals.llm_judge import judge_faithfulness
from ai.evals.retrieval_metrics import aggregate, hit_rate, precision_at_k, recall_at_k, reciprocal_rank
from ai.rag.pipeline import answer_query, build_context
from ai.rag.retriever import retrieve
from app.core.config import get_settings

GOLDEN_PATH = Path(__file__).parent / "datasets" / "golden.jsonl"
K = 5


def load_golden() -> list[dict]:
    return [json.loads(line) for line in GOLDEN_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


async def eval_retrieval(cases: list[dict], owner_id: UUID) -> dict:
    per_query = []
    for case in cases:
        hits = await retrieve(case["query"], owner_id=owner_id)
        retrieved_docs = [h.document_title for h in hits]
        relevant = set(case["relevant_docs"])
        per_query.append(
            {
                f"precision@{K}": precision_at_k(retrieved_docs, relevant, K),
                f"recall@{K}": recall_at_k(retrieved_docs, relevant, K),
                "mrr": reciprocal_rank(retrieved_docs, relevant),
                f"hit_rate@{K}": hit_rate(retrieved_docs, relevant, K),
            }
        )
    return aggregate(per_query)


async def eval_generation(cases: list[dict], owner_id: UUID) -> dict:
    scores = []
    for case in cases:
        result = await answer_query(case["query"], owner_id=owner_id, use_llm_rerank=False)
        context = build_context(result.chunks, max_tokens=6000)
        judged = await judge_faithfulness(case["query"], context, result.answer)
        scores.append(judged.score)
    valid = [s for s in scores if s > 0]
    return {
        "faithfulness_avg": round(sum(valid) / len(valid), 3) if valid else 0.0,
        "judged": len(valid),
        "failed": len(scores) - len(valid),
    }


async def main(skip_generation: bool) -> None:
    configured_owner = get_settings().eval_owner_id
    if not configured_owner:
        raise RuntimeError("Set EVAL_OWNER_ID to the user whose documents form the evaluation corpus")
    owner_id = UUID(configured_owner)
    cases = load_golden()
    print(f"Running evals over {len(cases)} golden cases...\n")

    retrieval_metrics = await eval_retrieval(cases, owner_id)
    print("Retrieval metrics:", json.dumps(retrieval_metrics, indent=2))

    generation_metrics = {}
    if not skip_generation:
        generation_metrics = await eval_generation(cases, owner_id)
        print("Generation metrics:", json.dumps(generation_metrics, indent=2))

    # Persist the run for trend tracking.
    from app.db.models import EvalRun
    from app.db.session import async_session_factory

    async with async_session_factory() as session:
        session.add(
            EvalRun(
                kind="full" if not skip_generation else "retrieval",
                metrics={**retrieval_metrics, **generation_metrics},
                dataset_size=len(cases),
            )
        )
        await session.commit()
    print("\nEval run stored.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-generation", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.skip_generation))
