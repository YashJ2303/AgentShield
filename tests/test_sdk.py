import pytest
import asyncio
import agentshield
from agentshield import trace_model_call, trace_tool_call


@pytest.fixture(autouse=True)
def setup_sdk_tracing_mode():
    agentshield.init(check_policy=False)
    yield



def test_sdk_sync_tracing():
    @trace_tool_call(name="calculator")
    def add(a: int, b: int) -> int:
        return a + b

    @trace_model_call(name="mock-llm")
    def generate_response(prompt: str) -> dict:
        ans = add(5, 7)
        return {"response": f"The answer to {prompt} is {ans}", "usage": {"prompt_tokens": 12, "completion_tokens": 8}}

    with agentshield.run(task_id="math-1", prompt_version="v1.0", model="mock-model") as ctx:
        assert ctx.run_id is not None
        res = generate_response("What is 5+7?")
        assert "12" in res["response"]

        # 2 spans: 1 model call, 1 tool call
        assert len(ctx.spans) == 2
        tool_span = next(s for s in ctx.spans if s["span_type"] == "tool")
        model_span = next(s for s in ctx.spans if s["span_type"] == "model")

        assert tool_span["name"] == "calculator"
        assert tool_span["input_payload"]["a"] == 5
        assert tool_span["input_payload"]["b"] == 7
        assert tool_span["output_payload"] == 12
        # Tool spans belong directly to the run, not to the model span
        assert tool_span["parent_span_id"] is None
        assert model_span["sequence_number"] == 1
        assert tool_span["sequence_number"] == 2

        assert model_span["name"] == "mock-llm"
        assert model_span["token_counts"]["prompt_tokens"] == 12
        assert model_span["token_counts"]["completion_tokens"] == 8
        assert ctx.running_steps == 1
        assert ctx.running_tokens == 20


@pytest.mark.asyncio
async def test_sdk_async_tracing():
    @trace_tool_call(name="async_search")
    async def async_search(query: str):
        await asyncio.sleep(0.01)
        return {"results": [f"Result for {query}"]}

    @trace_model_call(name="async-llm")
    async def async_agent_call(q: str):
        data = await async_search(q)
        return {"content": f"Found {len(data['results'])} items"}

    with agentshield.run(task_id="search-1") as ctx:
        out = await async_agent_call("python tutorials")
        assert "Found 1 items" in out["content"]
        assert len(ctx.spans) == 2
        tool_span = next(s for s in ctx.spans if s["span_type"] == "tool")
        assert tool_span["parent_span_id"] is None
        assert tool_span["sequence_number"] == 2


def test_sdk_error_recording():
    @trace_tool_call(name="failing_tool")
    def explode():
        raise ValueError("Simulated tool crash")

    with pytest.raises(ValueError):
        with agentshield.run(task_id="error-task") as ctx:
            explode()

    # The span should have captured the error message before exception escalated
    assert len(ctx.spans) == 1
    assert "Simulated tool crash" in ctx.spans[0]["error"]


def test_sdk_redaction_in_decorator():
    @trace_model_call(name="echo-llm")
    def echo_prompt(prompt: str):
        return f"Echo: {prompt}"

    with agentshield.run(task_id="redact-task") as ctx:
        echo_prompt("My secret is api_key: secret-value-1234567890")
        span = ctx.spans[0]
        assert "[REDACTED:API_KEY]" in str(span["input_payload"])
        assert "[REDACTED:API_KEY]" in str(span["output_payload"])
        assert span["redaction_count"] >= 2


def test_sdk_buffers_spans_when_server_unreachable():
    from agentshield.client import GatewayClient, GatewayConfig

    config = GatewayConfig(
        server_url="http://127.0.0.1:59998",
        timeout=0.1,
    )
    client = GatewayClient(config=config)

    dummy_spans = [
        {"id": "s1", "name": "tool_1", "span_type": "tool"},
        {"id": "s2", "name": "tool_2", "span_type": "tool"},
    ]

    # Ingest fails due to connection error; spans must be buffered locally
    result = client.ingest_spans(dummy_spans)
    assert result is None
    assert client.get_buffered_spans_count() == 2

    # Second failed ingest accumulates spans into buffer without data loss
    more_spans = [{"id": "s3", "name": "tool_3", "span_type": "tool"}]
    client.ingest_spans(more_spans)
    assert client.get_buffered_spans_count() == 3

    buffered_ids = [s["id"] for s in client.get_buffered_spans()]
    assert buffered_ids == ["s1", "s2", "s3"]
