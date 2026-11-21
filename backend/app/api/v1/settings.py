"""Authenticated, read-only view of effective runtime configuration."""
from urllib.parse import urlsplit

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core.config import get_settings

router = APIRouter()


@router.get("")
async def get_runtime_settings(user: CurrentUser):
    settings = get_settings()
    if settings.llm_provider == "azure":
        chat_model = settings.azure_openai_chat_deployment
        embedding_model = settings.azure_openai_embedding_deployment
        endpoint = settings.azure_openai_endpoint
        credentials_configured = bool(endpoint and settings.azure_openai_api_key)
    else:
        chat_model = settings.llm_chat_model
        embedding_model = settings.llm_embedding_model
        endpoint = settings.llm_base_url or "https://api.openai.com/v1"
        credentials_configured = bool(settings.llm_api_key)

    return {
        "provider": settings.llm_provider,
        "chat_model": chat_model,
        "embedding_model": embedding_model,
        "endpoint_host": urlsplit(endpoint).hostname if endpoint else None,
        "credentials_configured": credentials_configured,
        "embedding_dimensions": settings.embedding_dimensions,
        "generation": {
            "temperature": settings.llm_temperature,
            "max_completion_tokens": settings.llm_max_completion_tokens,
            "timeout_seconds": settings.llm_timeout_seconds,
            "max_retries": settings.llm_max_retries,
        },
        "retrieval": {
            "chunking_strategy": settings.chunking_strategy,
            "chunk_size_tokens": settings.chunk_size_tokens,
            "chunk_overlap_tokens": settings.chunk_overlap_tokens,
            "top_k": settings.retrieval_top_k,
            "rerank_top_k": settings.rerank_top_k,
            "max_context_tokens": settings.max_context_tokens,
            "query_rewriting_enabled": settings.rag_query_rewriting,
        },
    }
