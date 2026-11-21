"""FastAPI application factory and lifespan management."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import CortexError
from app.core.logging import configure_logging, get_logger
from app.core.telemetry import configure_telemetry
from app.db.session import engine
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.request_context import RequestContextMiddleware

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging()
    configure_telemetry(app)
    logger.info("startup", environment=settings.environment)
    # Ensure the Qdrant collection exists before serving traffic.
    from ai.rag.vectorstore import get_vector_store

    await get_vector_store().ensure_collection()
    yield
    await engine.dispose()
    logger.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.environment != "production" else None,
    )

    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(CortexError)
    async def domain_error_handler(request: Request, exc: CortexError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    # Prometheus metrics endpoint (scrapeable at /metrics).
    app.mount("/metrics", make_asgi_app())
    return app


app = create_app()
