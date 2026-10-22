import pytest
from datetime import datetime, timezone
from sdk.agentshield.otlp_exporter import init_otlp, export_otel_span, flush_otel


def test_otlp_span_export_and_attributes():
    tracer = init_otlp(service_name="test-agentshield")
    assert tracer is not None

    now = datetime.now(timezone.utc)
    # Ensure export_otel_span handles standard attributes cleanly without errors
    export_otel_span(
        name="test_model_step",
        span_type="model",
        run_id="run-otlp-123",
        started_at=now,
        ended_at=now,
        attributes={
            "gen_ai.request.model": "gpt-4o",
            "gen_ai.usage.prompt_tokens": 150,
            "gen_ai.usage.completion_tokens": 50,
            "agentshield.redaction_count": 2,
        },
        error=None,
    )

    # Test error status recording
    export_otel_span(
        name="test_tool_step",
        span_type="tool",
        run_id="run-otlp-123",
        started_at=now,
        ended_at=now,
        attributes={"tool.name": "file_reader"},
        error="File not found",
    )

    flush_otel()
