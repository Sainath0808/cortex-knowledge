"""Health and readiness probes (used by Kubernetes)."""
from fastapi import APIRouter
from sqlalchemy import text

from app.db.session import engine

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Liveness: process is up."""
    return {"status": "ok"}


@router.get("/health/ready")
async def ready() -> dict:
    """Readiness: dependencies are reachable."""
    checks = {}
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {e}"

    try:
        from app.middleware.rate_limit import get_redis

        await get_redis().ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"

    try:
        from ai.rag.vectorstore import get_vector_store

        await get_vector_store().client.get_collections()
        checks["qdrant"] = "ok"
    except Exception as e:
        checks["qdrant"] = f"error: {e}"

    healthy = all(v == "ok" for v in checks.values())
    return {"status": "ready" if healthy else "degraded", "checks": checks}
