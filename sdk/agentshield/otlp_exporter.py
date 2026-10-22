import logging
from typing import Optional, Any
from datetime import datetime
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, SpanProcessor
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import Status, StatusCode
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

logger = logging.getLogger("agentshield.otlp")

_tracer: Optional[trace.Tracer] = None
_provider: Optional[TracerProvider] = None


def init_otlp(service_name: str = "agentshield-agent", otlp_endpoint: Optional[str] = None) -> trace.Tracer:
    """Initialize OpenTelemetry tracer and optional OTLP exporter."""
    global _tracer, _provider

    resource = Resource.create({
        "service.name": service_name,
        "telemetry.sdk.name": "agentshield",
        "telemetry.sdk.language": "python",
    })
    _provider = TracerProvider(resource=resource)

    if otlp_endpoint:
        try:
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            processor = BatchSpanProcessor(exporter)
            _provider.add_span_processor(processor)
            logger.info("Configured OTLP exporter pointing to %s", otlp_endpoint)
        except Exception as e:
            logger.warning("Could not initialize OTLP exporter: %s", e)

    trace.set_tracer_provider(_provider)
    _tracer = trace.get_tracer("agentshield.sdk")
    return _tracer


def get_tracer() -> trace.Tracer:
    global _tracer
    if _tracer is None:
        _tracer = init_otlp()
    return _tracer


def export_otel_span(
    name: str,
    span_type: str,
    run_id: str,
    started_at: datetime,
    ended_at: datetime,
    attributes: Optional[dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    """Export an individual span via OpenTelemetry."""
    tracer = get_tracer()
    start_time_ns = int(started_at.timestamp() * 1e9)
    end_time_ns = int(ended_at.timestamp() * 1e9)

    span = tracer.start_span(
        name=name,
        start_time=start_time_ns,
    )

    span.set_attribute("agentshield.run_id", run_id)
    span.set_attribute("agentshield.span_type", span_type)

    if attributes:
        for k, v in attributes.items():
            if isinstance(v, (str, bool, int, float)):
                span.set_attribute(k, v)

    if error:
        span.set_status(Status(StatusCode.ERROR, description=str(error)))
        span.record_exception(Exception(str(error)))
    else:
        span.set_status(Status(StatusCode.OK))

    span.end(end_time=end_time_ns)


def flush_otel():
    """Flush pending OpenTelemetry spans."""
    global _provider
    if _provider:
        _provider.force_flush()
