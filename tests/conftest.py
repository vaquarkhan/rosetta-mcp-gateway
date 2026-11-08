import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from rosetta.proxy.otel import configure_tracing

EXPORTER = InMemorySpanExporter()


@pytest.fixture(scope="session", autouse=True)
def tracing():
    configure_tracing(EXPORTER)
    return EXPORTER
