"""Central LLM client wrapping Azure OpenAI.

Every model call in the platform goes through this module so that retries,
timeouts, cost tracking, latency measurement, and tracing are applied
uniformly. Nothing else in the codebase imports the openai SDK directly.
"""

import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any
from uuid import UUID

import structlog
from app.core.config import get_settings
from app.core.exceptions import UpstreamAIError
from app.core.logging import get_logger
from app.core.telemetry import get_tracer
from openai import (
    APIConnectionError,
    APITimeoutError,
    AsyncAzureOpenAI,
    AsyncOpenAI,
    RateLimitError,
)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from ai.llm.costs import estimate_cost

logger = get_logger(__name__)

RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError)


def build_provider_client(settings) -> tuple[AsyncOpenAI | AsyncAzureOpenAI, str, str]:
    """Provider seam: returns (client, chat_model, embedding_model).

    Everything downstream speaks the OpenAI wire protocol, so swapping Azure for
    OpenAI / an LLM gateway / Ollama is a config change, not a code change.
    """
    if settings.llm_provider == "azure":
        client = AsyncAzureOpenAI(
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            timeout=settings.llm_timeout_seconds,
            max_retries=0,  # we own retries via tenacity
        )
        return (
            client,
            settings.azure_openai_chat_deployment,
            settings.azure_openai_embedding_deployment,
        )

    client = AsyncOpenAI(
        base_url=settings.llm_base_url or None,  # None = api.openai.com
        api_key=settings.llm_api_key,
        timeout=settings.llm_timeout_seconds,
        max_retries=0,
    )
    return client, settings.llm_chat_model, settings.llm_embedding_model


@dataclass
class ChatResult:
    content: str | None
    tool_calls: list[Any] = field(default_factory=list)
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    raw: Any = None


class LLMClient:
    def __init__(self):
        s = get_settings()
        self._client, self._chat_deployment, self._embed_deployment = build_provider_client(s)
        self._embed_dims = s.embedding_dimensions
        # `dimensions` is an OpenAI/Azure API extension; local providers (Ollama)
        # reject unknown params. base_url set + provider=openai => assume no support.
        self._send_dimensions = s.llm_provider == "azure" or not s.llm_base_url
        self._max_attempts = s.llm_max_retries

    # ---------------- Chat ----------------

    async def chat(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.1,
        max_tokens: int | None = 1024,
        tools: list[dict] | None = None,
        response_format: dict | None = None,
        operation: str = "chat",
    ) -> ChatResult:
        @retry(
            retry=retry_if_exception_type(RETRYABLE),
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(multiplier=1, min=1, max=20),
            reraise=True,
        )
        async def _call():
            return await self._client.chat.completions.create(
                model=self._chat_deployment,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools or None,
                response_format=response_format,
            )

        start = time.perf_counter()
        with get_tracer().start_as_current_span(f"llm.{operation}") as span:
            span.set_attribute("llm.model", self._chat_deployment)
            try:
                resp = await _call()
            except RETRYABLE as e:
                logger.error("llm_call_failed", operation=operation, error=str(e))
                raise UpstreamAIError() from e

            latency_ms = (time.perf_counter() - start) * 1000
            usage = resp.usage
            cost = estimate_cost(
                self._chat_deployment, usage.prompt_tokens, usage.completion_tokens
            )
            span.set_attribute("llm.prompt_tokens", usage.prompt_tokens)
            span.set_attribute("llm.completion_tokens", usage.completion_tokens)
            span.set_attribute("llm.cost_usd", cost)

        choice = resp.choices[0].message
        result = ChatResult(
            content=choice.content,
            tool_calls=list(choice.tool_calls or []),
            model=self._chat_deployment,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
            raw=resp,
        )
        await self._record(operation, result)
        return result

    # ---------------- Embeddings ----------------

    async def embed(self, texts: list[str], *, operation: str = "embed") -> list[list[float]]:
        @retry(
            retry=retry_if_exception_type(RETRYABLE),
            stop=stop_after_attempt(self._max_attempts),
            wait=wait_exponential(multiplier=1, min=1, max=20),
            reraise=True,
        )
        async def _call():
            kwargs = {"dimensions": self._embed_dims} if self._send_dimensions else {}
            return await self._client.embeddings.create(
                model=self._embed_deployment, input=texts, **kwargs
            )

        start = time.perf_counter()
        with get_tracer().start_as_current_span("llm.embed") as span:
            span.set_attribute("llm.model", self._embed_deployment)
            span.set_attribute("embed.batch_size", len(texts))
            try:
                resp = await _call()
            except RETRYABLE as e:
                logger.error("embed_call_failed", error=str(e))
                raise UpstreamAIError() from e
            latency_ms = (time.perf_counter() - start) * 1000

        cost = estimate_cost(self._embed_deployment, resp.usage.prompt_tokens, 0)
        await self._record(
            operation,
            ChatResult(
                content=None,
                model=self._embed_deployment,
                prompt_tokens=resp.usage.prompt_tokens,
                cost_usd=cost,
                latency_ms=latency_ms,
            ),
        )
        return [item.embedding for item in resp.data]

    async def _record(self, operation: str, result: ChatResult) -> None:
        try:
            from app.db.repositories.usage import record_usage

            await record_usage(
                operation=operation,
                model=result.model,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                cost_usd=result.cost_usd,
                latency_ms=result.latency_ms,
                request_id=structlog.contextvars.get_contextvars().get("request_id"),
                user_id=(
                    UUID(user_id)
                    if (user_id := structlog.contextvars.get_contextvars().get("user_id"))
                    else None
                ),
            )
        except Exception:
            # Cost tracking must never break the request path.
            logger.warning("usage_record_failed", operation=operation)


@lru_cache
def get_llm_client() -> LLMClient:
    return LLMClient()
