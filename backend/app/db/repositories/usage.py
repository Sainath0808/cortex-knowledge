"""LLM usage repository — cost and latency tracking.

Writes use their own short-lived session so a usage record is never lost
to a rolled-back request transaction.
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select

from app.db.models import LLMUsage
from app.db.session import async_session_factory


async def record_usage(
    *,
    operation: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_usd: float,
    latency_ms: float,
    request_id: str | None = None,
    user_id: UUID | None = None,
) -> None:
    async with async_session_factory() as session:
        session.add(
            LLMUsage(
                operation=operation,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cost_usd=cost_usd,
                latency_ms=latency_ms,
                request_id=request_id,
                user_id=user_id,
            )
        )
        await session.commit()


async def usage_summary(days: int = 7) -> list[dict]:
    since = datetime.now(UTC) - timedelta(days=days)
    async with async_session_factory() as session:
        result = await session.execute(
            select(
                LLMUsage.operation,
                LLMUsage.model,
                func.count(LLMUsage.id).label("calls"),
                func.sum(LLMUsage.prompt_tokens).label("prompt_tokens"),
                func.sum(LLMUsage.completion_tokens).label("completion_tokens"),
                func.sum(LLMUsage.cost_usd).label("cost_usd"),
                func.avg(LLMUsage.latency_ms).label("avg_latency_ms"),
            )
            .where(LLMUsage.created_at >= since)
            .group_by(LLMUsage.operation, LLMUsage.model)
        )
        return [dict(row._mapping) for row in result]
