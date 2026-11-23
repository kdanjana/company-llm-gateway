"""Streaming ("stream": true): Server-Sent Events, usage logged at the end."""
from decimal import Decimal

from gateway.bedrock_client import BedrockError
from gateway.models import UsageLog

from .conftest import MODEL, chat_body, post_chat, sse_events


def test_stream_sends_text_pieces_then_done_with_usage(api, raw_key, price, fake_bedrock):
    response = post_chat(api, raw_key, chat_body(stream=True))

    assert response.status_code == 200
    assert response["Content-Type"] == "text/event-stream"
    events = sse_events(response)
    assert [e["text"] for e in events if e["type"] == "text"] == ["Hel", "lo!"]

    done = events[-1]
    assert done["type"] == "done"
    assert done["usage"] == {"input_tokens": 1000, "output_tokens": 200, "cost_usd": "0.002000"}

    log = UsageLog.objects.get()
    assert log.status == UsageLog.Status.OK
    assert log.streamed is True
    assert log.cost_usd == Decimal("0.002")


def test_error_before_the_first_word_is_a_normal_http_error(api, raw_key, price, fake_bedrock):
    fake_bedrock.errors[MODEL] = BedrockError("ThrottlingException", "slow down", 429)

    response = post_chat(api, raw_key, chat_body(stream=True))

    assert response.status_code == 429
    assert response.data["error"]["code"] == "ThrottlingException"


def test_error_in_the_middle_of_the_stream_is_an_error_event(api, raw_key, price, fake_bedrock):
    fake_bedrock.stream_error = BedrockError("ModelTimeoutException", "took too long", 504)

    events = sse_events(post_chat(api, raw_key, chat_body(stream=True)))

    assert events[-1] == {"type": "error", "error": {"code": "ModelTimeoutException", "message": "The model did not answer in time."}}
    log = UsageLog.objects.get()
    assert log.status == UsageLog.Status.ERROR
    assert log.streamed is True


def test_budget_block_applies_to_streaming_too(api, raw_key, department, price, fake_bedrock):
    department.monthly_budget_usd = Decimal("0")
    department.save()
    assert post_chat(api, raw_key, chat_body(stream=True)).status_code == 403
