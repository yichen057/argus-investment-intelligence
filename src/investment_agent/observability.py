from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from sqlalchemy import Engine

from investment_agent.config import Settings


def configure_observability(
    app: FastAPI,
    engine: Engine,
    settings: Settings,
) -> Any | None:
    """Configure OTLP tracing when an endpoint is supplied; stay no-op locally."""
    if not settings.otel_exporter_otlp_endpoint:
        return None

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": "argus-api",
                "deployment.environment": settings.env,
            }
        )
    )
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint)
        )
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    SQLAlchemyInstrumentor().instrument(engine=engine, tracer_provider=provider)
    return provider
