"""OpenTelemetry setup: traces for API -> agent -> RAG -> LLM call chains.

A single trace follows a chat request through FastAPI, the agent graph,
retrieval, and each LLM call, so latency and failures are attributable
to a specific stage.
"""
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from app.core.config import get_settings

_tracer: trace.Tracer | None = None


def configure_telemetry(app=None) -> None:
    global _tracer
    settings = get_settings()
    if not settings.otel_enabled:
        _tracer = trace.get_tracer("cortex")  # no-op tracer
        return

    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    resource = Resource.create(
        {"service.name": "cortex-api", "deployment.environment": settings.environment}
    )
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint))
    )
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer("cortex")

    if app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)


def get_tracer() -> trace.Tracer:
    return _tracer or trace.get_tracer("cortex")
