"""Fallback: if the model is busy/unavailable and a fallback model is set, retry once on the fallback."""
from gateway.bedrock_client import BedrockError
from gateway.models import ModelPrice, UsageLog

from .conftest import FALLBACK, MODEL, chat_body, post_chat, sse_events


def throttled():
    return BedrockError("ThrottlingException", "Too many requests", 429)


def test_throttled_model_falls_back(api, raw_key, price, fallback_price, fake_bedrock):
    fake_bedrock.errors[MODEL] = throttled()

    response = post_chat(api, raw_key)

    assert response.status_code == 200
    assert response.data["model"] == MODEL
    assert response.data["served_model"] == FALLBACK
    assert response.data["fallback_used"] is True
    # Priced with the FALLBACK model's prices: 1000 * 0.002/1k + 200 * 0.010/1k = 0.004
    assert response.data["usage"]["cost_usd"] == "0.004000"
    assert [c["model_id"] for c in fake_bedrock.calls] == [MODEL, FALLBACK]

    log = UsageLog.objects.get()
    assert (log.model_id, log.served_model_id, log.fallback_used) == (MODEL, FALLBACK, True)


def test_no_fallback_configured_returns_429(api, raw_key, price, fake_bedrock):
    fake_bedrock.errors[MODEL] = throttled()
    assert post_chat(api, raw_key).status_code == 429
    assert len(fake_bedrock.calls) == 1


def test_bad_request_is_not_retried_on_fallback(api, raw_key, price, fallback_price, fake_bedrock):
    fake_bedrock.errors[MODEL] = BedrockError("ValidationException", "bad input", 400)
    assert post_chat(api, raw_key).status_code == 400
    assert len(fake_bedrock.calls) == 1


def test_disabled_fallback_is_not_used(api, raw_key, price, fallback_price, fake_bedrock):
    ModelPrice.objects.filter(model_id=FALLBACK).update(is_enabled=False)
    fake_bedrock.errors[MODEL] = throttled()
    assert post_chat(api, raw_key).status_code == 429


def test_both_models_failing_returns_error(api, raw_key, price, fallback_price, fake_bedrock):
    fake_bedrock.errors[MODEL] = throttled()
    fake_bedrock.errors[FALLBACK] = BedrockError("ServiceUnavailableException", "down", 503)

    response = post_chat(api, raw_key)

    assert response.status_code == 503
    assert UsageLog.objects.get().status == UsageLog.Status.ERROR


def test_streaming_falls_back_before_the_first_word(api, raw_key, price, fallback_price, fake_bedrock):
    fake_bedrock.errors[MODEL] = throttled()

    events = sse_events(post_chat(api, raw_key, chat_body(stream=True)))

    assert events[-1]["type"] == "done"
    assert events[-1]["served_model"] == FALLBACK
    assert events[-1]["fallback_used"] is True
