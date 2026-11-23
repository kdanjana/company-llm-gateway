"""Answer cache: same request + same department -> saved answer, no model call, no cost."""
from gateway.models import UsageLog

from .conftest import chat_body, post_chat, sse_events


def test_identical_request_is_answered_from_cache(api, raw_key, price, fake_bedrock):
    first = post_chat(api, raw_key)
    second = post_chat(api, raw_key)

    assert len(fake_bedrock.calls) == 1
    assert first.data["cached"] is False
    assert second.data["cached"] is True
    assert second.data["content"] == "Hello!"
    assert second.data["usage"]["cost_usd"] == "0.000000"

    cached_log = UsageLog.objects.get(cached=True)
    assert cached_log.cost_usd == 0
    assert cached_log.status == UsageLog.Status.OK


def test_cache_can_be_skipped(api, raw_key, price, fake_bedrock):
    post_chat(api, raw_key, chat_body(cache=False))
    post_chat(api, raw_key, chat_body(cache=False))
    assert len(fake_bedrock.calls) == 2


def test_different_question_is_not_cached(api, raw_key, price, fake_bedrock):
    post_chat(api, raw_key, chat_body(messages=[{"role": "user", "content": "Hi"}]))
    post_chat(api, raw_key, chat_body(messages=[{"role": "user", "content": "Hi there"}]))
    assert len(fake_bedrock.calls) == 2


def test_departments_never_share_cached_answers(api, raw_key, other_raw_key, price, fake_bedrock):
    post_chat(api, raw_key)
    response = post_chat(api, other_raw_key)
    assert response.data["cached"] is False
    assert len(fake_bedrock.calls) == 2


def test_streaming_requests_are_not_cached(api, raw_key, price, fake_bedrock):
    sse_events(post_chat(api, raw_key, chat_body(stream=True)))
    sse_events(post_chat(api, raw_key, chat_body(stream=True)))
    assert len(fake_bedrock.calls) == 2
