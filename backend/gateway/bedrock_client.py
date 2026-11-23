"""Calls Claude models on AWS Bedrock through boto3's Converse API.

- converse()         -> the whole answer at once
- converse_stream()  -> yields {"type": "text", "text": ...} pieces, then one {"type": "usage", ...}

Credentials: only the access keys from .env (no AWS CLI profiles), same as the Knowledge Hub project.

Retries: at most 3 attempts ("standard" mode). A gateway should not hide long waits from the calling app:
if Bedrock keeps throttling, the gateway tries the fallback model (if set) or returns a clear 429.

Fake mode: with DJANGO_DEBUG=true and GATEWAY_FAKE_BEDROCK=true, get_client() returns FakeBedrockClient,
which answers instantly without AWS. Used for load tests and UI demos; it costs nothing.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterator

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings

log = logging.getLogger("gateway")

# Bedrock error code -> HTTP status the gateway returns to the calling app.
_HTTP_STATUS_BY_CODE = {
    "ThrottlingException": 429,
    "ServiceQuotaExceededException": 429,
    "ValidationException": 400,
    "ModelNotReadyException": 503,
    "ServiceUnavailableException": 503,
    "ModelTimeoutException": 504,
}


class BedrockError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 502):
        super().__init__(message)
        self.code = code
        self.http_status = http_status


def _error(code: str, message: str) -> BedrockError:
    code = code[:1].upper() + code[1:]  # stream events use "throttlingException", API errors "ThrottlingException"
    return BedrockError(code, message, _HTTP_STATUS_BY_CODE.get(code, 502))


def _from_client_error(exc: ClientError) -> BedrockError:
    error = exc.response.get("Error", {})
    return _error(error.get("Code", "ClientError"), error.get("Message", str(exc)))


@dataclass
class ChatResult:
    text: str
    stop_reason: str
    input_tokens: int
    output_tokens: int
    latency_ms: int


class BedrockClient:
    def __init__(self) -> None:
        if not settings.AWS_ACCESS_KEY_ID or not settings.AWS_SECRET_ACCESS_KEY:
            raise BedrockError("NotConfigured", "AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY missing in .env", 500)

        # boto3 reads AWS_PROFILE from the environment even when keys are passed; an empty or unknown
        # value crashes it (ProfileNotFound). This project never uses profiles, so remove it.
        os.environ.pop("AWS_PROFILE", None)

        self.runtime = boto3.client(
            "bedrock-runtime",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            aws_session_token=settings.AWS_SESSION_TOKEN or None,
            config=BotoConfig(
                retries={"max_attempts": 3, "mode": "standard"},
                connect_timeout=5,
                read_timeout=settings.BEDROCK_READ_TIMEOUT,
            ),
        )

    @staticmethod
    def _kwargs(model_id: str, messages: list[dict[str, Any]], system: str | None, max_tokens: int) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "modelId": model_id,
            "messages": messages,
            "inferenceConfig": {"maxTokens": max_tokens},
        }
        if system:
            kwargs["system"] = [{"text": system}]
        return kwargs

    def converse(self, model_id: str, messages: list[dict[str, Any]], system: str | None, max_tokens: int) -> ChatResult:
        start = time.monotonic()
        try:
            response = self.runtime.converse(**self._kwargs(model_id, messages, system, max_tokens))
        except ClientError as exc:
            raise _from_client_error(exc) from exc
        except BotoCoreError as exc:  # network problems, timeouts
            raise BedrockError(type(exc).__name__, str(exc), 504) from exc

        content = response.get("output", {}).get("message", {}).get("content", [])
        usage = response.get("usage", {})
        return ChatResult(
            text="".join(block.get("text", "") for block in content),
            stop_reason=response.get("stopReason", ""),
            input_tokens=usage.get("inputTokens", 0),
            output_tokens=usage.get("outputTokens", 0),
            latency_ms=int((time.monotonic() - start) * 1000),
        )

    def converse_stream(
        self, model_id: str, messages: list[dict[str, Any]], system: str | None, max_tokens: int
    ) -> Iterator[dict[str, Any]]:
        start = time.monotonic()
        usage: dict[str, Any] = {}
        stop_reason = ""
        try:
            response = self.runtime.converse_stream(**self._kwargs(model_id, messages, system, max_tokens))
            for event in response["stream"]:
                if "contentBlockDelta" in event:
                    text = event["contentBlockDelta"].get("delta", {}).get("text")
                    if text:
                        yield {"type": "text", "text": text}
                elif "messageStop" in event:
                    stop_reason = event["messageStop"].get("stopReason", "")
                elif "metadata" in event:
                    usage = event["metadata"].get("usage", {}) or {}
                else:
                    for key, value in event.items():
                        if key.endswith("Exception"):
                            message = value.get("message", "") if isinstance(value, dict) else str(value)
                            raise _error(key, message)
        except ClientError as exc:
            raise _from_client_error(exc) from exc
        except BotoCoreError as exc:
            raise BedrockError(type(exc).__name__, str(exc), 504) from exc

        yield {
            "type": "usage",
            "input_tokens": usage.get("inputTokens", 0),
            "output_tokens": usage.get("outputTokens", 0),
            "stop_reason": stop_reason,
            "latency_ms": int((time.monotonic() - start) * 1000),
        }


class FakeBedrockClient:
    """Answers instantly (plus GATEWAY_FAKE_LATENCY_MS) without calling AWS. Development only."""

    @staticmethod
    def _answer(model_id: str) -> str:
        return f"This is a fake answer from {model_id}. No model was called."

    @staticmethod
    def _input_tokens(messages: list[dict[str, Any]], system: str | None) -> int:
        chars = sum(len(block.get("text", "")) for m in messages for block in m["content"]) + len(system or "")
        return max(1, chars // 4)  # rough rule: about 4 characters per token

    @staticmethod
    def _wait() -> None:
        if settings.GATEWAY_FAKE_LATENCY_MS:
            time.sleep(settings.GATEWAY_FAKE_LATENCY_MS / 1000)

    def converse(self, model_id: str, messages: list[dict[str, Any]], system: str | None, max_tokens: int) -> ChatResult:
        start = time.monotonic()
        self._wait()
        text = self._answer(model_id)
        return ChatResult(
            text=text,
            stop_reason="end_turn",
            input_tokens=self._input_tokens(messages, system),
            output_tokens=max(1, len(text) // 4),
            latency_ms=int((time.monotonic() - start) * 1000),
        )

    def converse_stream(
        self, model_id: str, messages: list[dict[str, Any]], system: str | None, max_tokens: int
    ) -> Iterator[dict[str, Any]]:
        start = time.monotonic()
        self._wait()
        text = self._answer(model_id)
        for word in text.split(" "):
            yield {"type": "text", "text": word + " "}
        yield {
            "type": "usage",
            "input_tokens": self._input_tokens(messages, system),
            "output_tokens": max(1, len(text) // 4),
            "stop_reason": "end_turn",
            "latency_ms": int((time.monotonic() - start) * 1000),
        }


@lru_cache(maxsize=1)
def get_client() -> BedrockClient | FakeBedrockClient:
    """One shared client per process (boto3 clients are thread-safe and slow to create)."""
    if settings.DEBUG and settings.GATEWAY_FAKE_BEDROCK:
        log.warning("GATEWAY_FAKE_BEDROCK is on: answers are fake, no model is called")
        return FakeBedrockClient()
    return BedrockClient()
