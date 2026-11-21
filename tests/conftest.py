"""Shared test fixtures.

Tests use SQLite (aiosqlite) for speed and never call real Azure OpenAI —
the LLM client and vector store are faked at the boundary.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "test-secret")
os.environ.setdefault("ENVIRONMENT", "test")

import pytest
import pytest_asyncio
from app.db.models import Base
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session, monkeypatch):
    """API test client with DB overridden and external services stubbed."""
    from app.db.session import get_db
    from app.main import create_app

    app = create_app()

    async def override_get_db():
        yield db_session
        await db_session.commit()

    app.dependency_overrides[get_db] = override_get_db

    # Don't run the real lifespan (it touches Qdrant); no-op middlewared Redis
    # fails open by design.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def fake_chunks():
    from ai.rag.vectorstore import ScoredChunk

    return [
        ScoredChunk(
            chunk_id=f"chunk-{i}",
            document_id=f"doc-{i % 2}",
            document_title=f"Doc {i % 2}",
            content=f"Relevant content number {i} about the remote work policy.",
            score=1.0 - i * 0.1,
        )
        for i in range(5)
    ]
