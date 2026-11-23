"""POST /api/v1/chat: API key check, validation, model allow-list, usage + cost logging, error mapping."""
from decimal import Decimal

from gateway.bedrock_client import BedrockError
from gateway.models import ApiKey, ModelPrice, UsageLog

from .conftest import MODEL, chat_body, post_chat

# ---------- success ----------

def test_success_returns_answer_and_logs_usage_and_cost(api, raw_key, price, fake_bedrock):
    response = post_chat(api, raw_key)

    assert response.status_code == 200
    assert response.data["content"] == "Hello!"
    assert response.data["served_model"] == MODEL
    assert response.data["cached"] is False
    # 1000 input tokens * $0.001/1k + 200 output tokens * $0.005/1k = 0.001 + 0.001
    assert response.data["usage"] == {"input_tokens": 1000, "output_tokens": 200, "cost_usd": "0.002000"}

    log = UsageLog.objects.get()
    assert log.status == UsageLog.Status.OK
    assert log.department.name == "Sales"
    assert log.served_model_id == MODEL
    assert (log.input_tokens, log.output_tokens) == (1000, 200)
    assert log.cost_usd == Decimal("0.002")
    assert log.latency_ms == 42


def test_messages_are_sent_to_bedrock_in_converse_format(api, raw_key, price, fake_bedrock):
    post_chat(api, raw_key, chat_body(system="Be brief.", max_tokens=50))

    call = fake_bedrock.calls[0]
    assert call["model_id"] == MODEL
    assert call["messages"] == [{"role": "user", "content": [{"text": "Hi"}]}]
    assert call["system"] == "Be brief."
    assert call["max_tokens"] == 50


def test_key_last_used_is_recorded(api, raw_key, price, fake_bedrock):
    post_chat(api, raw_key)
    assert ApiKey.objects.get().last_used_at is not None


# ---------- API key ----------

def test_missing_key_is_401_in_gateway_error_format(api, price, fake_bedrock):
    response = post_chat(api)
    assert response.status_code == 401
    assert response.data["error"]["code"] == "not_authenticated"
    assert fake_bedrock.calls == []


def test_wrong_key_is_401(api, raw_key, price, fake_bedrock):
    assert post_chat(api, "gw_not-a-real-key").status_code == 401
    assert fake_bedrock.calls == []


def test_disabled_key_is_401(api, raw_key, price, fake_bedrock):
    ApiKey.objects.update(is_active=False)
    assert post_chat(api, raw_key).status_code == 401


def test_disabled_department_is_401(api, raw_key, department, price, fake_bedrock):
    department.is_active = False
    department.save()
    assert post_chat(api, raw_key).status_code == 401


def test_raw_key_is_never_stored(raw_key):
    stored = ApiKey.objects.get()
    assert raw_key.startswith("gw_")
    assert stored.key_hash != raw_key
    assert raw_key not in (stored.key_hash, stored.prefix)


# ---------- model allow-list ----------

def test_model_without_price_is_refused(api, raw_key, fake_bedrock):
    response = post_chat(api, raw_key)  # no ModelPrice row
    assert response.status_code == 400
    assert response.data["error"]["code"] == "model_not_allowed"
    assert fake_bedrock.calls == []
    assert UsageLog.objects.count() == 0


def test_disabled_model_is_refused(api, raw_key, price, fake_bedrock):
    ModelPrice.objects.update(is_enabled=False)
    assert post_chat(api, raw_key).status_code == 400


# ---------- request validation ----------

def test_first_message_must_be_user(api, raw_key, price, fake_bedrock):
    data = chat_body(messages=[{"role": "assistant", "content": "Hi"}, {"role": "user", "content": "Hello"}])
    response = post_chat(api, raw_key, data)
    assert response.status_code == 400
    assert response.data["error"]["code"] == "invalid_request"
    assert "messages" in response.data["error"]["details"]
    assert fake_bedrock.calls == []


def test_roles_must_alternate(api, raw_key, price, fake_bedrock):
    data = chat_body(messages=[{"role": "user", "content": "a"}, {"role": "user", "content": "b"}])
    assert post_chat(api, raw_key, data).status_code == 400


def test_max_tokens_above_limit_is_refused(api, raw_key, price, fake_bedrock, settings):
    assert post_chat(api, raw_key, chat_body(max_tokens=settings.GATEWAY_MAX_TOKENS + 1)).status_code == 400


# ---------- Bedrock errors ----------

def test_throttling_returns_429_and_logs_error(api, raw_key, price, fake_bedrock):
    fake_bedrock.errors[MODEL] = BedrockError("ThrottlingException", "Too many requests", 429)

    response = post_chat(api, raw_key)

    assert response.status_code == 429
    assert response.data["error"]["code"] == "ThrottlingException"
    log = UsageLog.objects.get()
    assert log.status == UsageLog.Status.ERROR
    assert log.error_code == "ThrottlingException"
    assert log.cost_usd == 0


def test_raw_aws_message_is_not_returned_to_caller(api, raw_key, price, fake_bedrock):
    fake_bedrock.errors[MODEL] = BedrockError("AccessDeniedException", "User arn:aws:iam::123:user/x is not authorized", 502)

    response = post_chat(api, raw_key)

    assert response.status_code == 502
    assert "arn:aws" not in response.data["error"]["message"]
