"""Shared test setup. Bedrock is replaced by a fake, so tests never call AWS or cost money."""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from accounts.models import Profile
from gateway.bedrock_client import ChatResult
from gateway.models import ApiKey, Department, ModelPrice

MODEL = "test-model"
FALLBACK = "fallback-model"
CHAT_URL = "/api/v1/chat"


class FakeBedrock:
    """Stands in for BedrockClient. Records every call.
    errors: {model_id: BedrockError} -> calling that model raises the error.
    stream_error: raised in the middle of a stream (after the first text pieces)."""

    def __init__(self):
        self.calls = []
        self.errors = {}
        self.stream_error = None
        self.text = "Hello!"
        self.input_tokens = 1000
        self.output_tokens = 200

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs["model_id"] in self.errors:
            raise self.errors[kwargs["model_id"]]
        return ChatResult(self.text, "end_turn", self.input_tokens, self.output_tokens, 42)

    def converse_stream(self, **kwargs):
        # A generator, like the real one: nothing runs until the first next(), so errors show up there.
        self.calls.append(kwargs)
        if kwargs["model_id"] in self.errors:
            raise self.errors[kwargs["model_id"]]
        yield {"type": "text", "text": "Hel"}
        yield {"type": "text", "text": "lo!"}
        if self.stream_error:
            raise self.stream_error
        yield {
            "type": "usage",
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "stop_reason": "end_turn",
            "latency_ms": 42,
        }


@pytest.fixture(autouse=True)
def local_cache(settings):
    """Every test gets an empty in-memory cache (never the Redis of the running app)."""
    settings.CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "tests"}}
    from django.core.cache import cache

    cache.clear()


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def department(db):
    return Department.objects.create(name="Sales")


@pytest.fixture
def other_department(db):
    return Department.objects.create(name="HR")


@pytest.fixture
def raw_key(department):
    _, raw = ApiKey.issue(department, name="sales-bot")
    return raw


@pytest.fixture
def other_raw_key(other_department):
    _, raw = ApiKey.issue(other_department, name="hr-bot")
    return raw


@pytest.fixture
def price(db):
    return ModelPrice.objects.create(
        model_id=MODEL,
        input_price_per_1k=Decimal("0.001"),
        output_price_per_1k=Decimal("0.005"),
    )


@pytest.fixture
def fallback_price(price):
    fallback = ModelPrice.objects.create(
        model_id=FALLBACK,
        input_price_per_1k=Decimal("0.002"),
        output_price_per_1k=Decimal("0.010"),
    )
    price.fallback_model_id = FALLBACK
    price.save()
    return fallback


@pytest.fixture
def fake_bedrock(monkeypatch):
    fake = FakeBedrock()
    monkeypatch.setattr("gateway.services.get_client", lambda: fake)
    return fake


def chat_body(**overrides):
    data = {"model": MODEL, "messages": [{"role": "user", "content": "Hi"}]}
    data.update(overrides)
    return data


def post_chat(api, raw_key=None, data=None):
    headers = {"HTTP_AUTHORIZATION": f"Bearer {raw_key}"} if raw_key else {}
    return api.post(CHAT_URL, data or chat_body(), format="json", **headers)


def sse_events(response) -> list[dict]:
    """Reads a streaming response and returns its events as dicts."""
    import json

    text = b"".join(response.streaming_content).decode()
    return [json.loads(line[len("data: "):]) for line in text.splitlines() if line.startswith("data: ")]


# ---------- dashboard users ----------

def make_user(username, role, department=None):
    user = get_user_model().objects.create_user(username=username, password="a-long-test-password-1")
    Profile.objects.create(user=user, role=role, department=department)
    return user


@pytest.fixture
def gw_admin(db):
    return make_user("admin1", Profile.Role.ADMIN)


@pytest.fixture
def sales_head(department):
    return make_user("sales_head", Profile.Role.HEAD, department)
