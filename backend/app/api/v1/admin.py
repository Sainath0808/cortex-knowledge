"""Admin endpoints: usage/cost dashboards and eval history. Admin-only."""
from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.deps import DB, require_role
from app.db.models import EvalRun, UserRole
from app.db.repositories.usage import usage_summary

router = APIRouter(dependencies=[require_role(UserRole.admin)])


@router.get("/usage")
async def get_usage(days: int = Query(default=7, ge=1, le=365)):
    """LLM usage grouped by operation and model: calls, tokens, cost, latency."""
    return await usage_summary(days=days)


@router.get("/evals")
async def list_eval_runs(db: DB, limit: int = Query(default=20, ge=1, le=100)):
    result = await db.execute(select(EvalRun).order_by(EvalRun.created_at.desc()).limit(limit))
    return [
        {
            "id": str(r.id),
            "kind": r.kind,
            "metrics": r.metrics,
            "dataset_size": r.dataset_size,
            "created_at": r.created_at.isoformat(),
        }
        for r in result.scalars()
    ]
