"""OpenTelemetry spans for method, upstream server, and catalog cache."""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

_configured = False


def configure_tracing(exporter=None) -> None:
    """Install a tracer provider once. Tests pass an in-memory exporter."""
    global _configured
    if _configured:
        return
    provider = TracerProvider()
    if exporter is not None:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _configured = True


def tracer():
    return trace.get_tracer("rosetta.gateway")
