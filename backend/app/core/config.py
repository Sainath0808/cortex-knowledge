"""Application configuration.

Single source of truth for all runtime settings. Values come from environment
variables (or a local .env file). Never hardcode secrets anywhere else.
"""
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "Cortex"
    environment: str = "local"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Data stores
    database_url: str = "postgresql+asyncpg://cortex:cortex@localhost:5432/cortex"
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "cortex_chunks"
    mcp_owner_id: str = ""
    eval_owner_id: str = ""

    # LLM provider selection:
    #   "azure"  -> Azure OpenAI (azure_openai_* settings below)
    #   "openai" -> any OpenAI-compatible endpoint: OpenAI, an LLM gateway (LiteLLM),
    #               OpenRouter, Groq, or local Ollama (http://localhost:11434/v1)
    llm_provider: Literal["azure", "openai"] = "azure"
    llm_base_url: str = ""          # only for provider=openai; empty = api.openai.com
    llm_api_key: str = ""           # provider=openai key (or gateway virtual key)
    llm_chat_model: str = "gpt-4o"  # provider=openai model names
    llm_embedding_model: str = "text-embedding-3-large"

    # Azure OpenAI
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_api_version: str = "2024-06-01"
    azure_openai_chat_deployment: str = "gpt-4o"
    azure_openai_embedding_deployment: str = "text-embedding-3-large"
    embedding_dimensions: int = 3072

    # LLM resilience
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 3
    llm_temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    llm_max_completion_tokens: int = Field(default=1024, ge=1, le=32768)

    # RAG tuning
    chunking_strategy: Literal["fixed", "recursive", "semantic", "structure_aware"] = "recursive"
    chunk_size_tokens: int = 512
    chunk_overlap_tokens: int = 64
    retrieval_top_k: int = 12
    rerank_top_k: int = 5
    max_context_tokens: int = 6000
    rag_query_rewriting: bool = True

    # Auth
    jwt_secret_key: str = "dev-only-secret"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Rate limiting
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    # Observability
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"


@lru_cache
def get_settings() -> Settings:
    return Settings()
