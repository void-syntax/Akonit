"""OpenTelemetry distributed tracing setup."""

from __future__ import annotations

import sys
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def setup_tracing(app: FastAPI | None = None, engine=None) -> TracerProvider:
    """Initialize OpenTelemetry tracer provider and instrument FastAPI + SQLAlchemy."""
    resource = Resource.create({"service.name": "signal-radar-backend"})
    provider = TracerProvider(resource=resource)
    
    # Exporting every SQL span to the console is noisy and costly for a local
    # desktop install. Enable it only when explicitly diagnosing a problem.
    if settings.otel_console_exporter_enabled and "pytest" not in sys.modules:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    
    trace.set_tracer_provider(provider)

    if app is not None:
        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI instrumented with OpenTelemetry")

    if engine is not None:
        sync_engine = getattr(engine, "sync_engine", engine)
        SQLAlchemyInstrumentor().instrument(engine=sync_engine)
        logger.info("SQLAlchemy instrumented with OpenTelemetry")

    return provider


def get_tracer(name: str = "signal-radar"):
    """Get an OpenTelemetry tracer."""
    return trace.get_tracer(name)
