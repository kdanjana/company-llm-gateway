"""The gateway's request flow, shared by normal and streaming requests.

  1. model allowed?                 ModelPrice row, enabled                 -> else 400 model_not_allowed
  2. mask personal data             pii.py                                  -> the model never sees it
  3. budget left?                   budgets.py                              -> else 403 budget_exceeded (logged "blocked")
  4. answered recently?             cache.py (not for streaming)            -> saved answer, cost 0
  5. call the model                 if it is busy/down and a fallback model is set, try the fallback once
  6. log usage + cost, update the department's budget alerts
"""
from __future__ import annotations

import itertools
import json
import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterator

from . import budgets, cache, pii
from .bedrock_client import BedrockError, get_client
from .exceptions import GatewayError
from .models import ApiKey, Department, ModelPrice, UsageLog

log = logging.getLogger("gateway")

ZERO_COST = Decimal("0.000000")

# Errors worth retrying on another model: rate limited, unavailable, timed out.
# Not 400 (the request itself is wrong; another model would refuse it too).
RETRYABLE_STATUSES = {429, 503, 504}

# What the calling app is told. The raw AWS message stays in our logs only.
PUBLIC_ERROR_MESSAGES = {
    400: "The model rejected the request.",
    429: "The model is busy (rate limited). Retry after a short wait.",
    500: "The gateway is not configured correctly.",
    503: "The model is temporarily unavailable.",
    504: "The model did not answer in time.",
}


@dataclass
class ChatRequest:
    api_key: ApiKey
    department: Department
    price: ModelPrice          # the model the app asked for
    messages: list[dict]       # Bedrock Converse format, already masked
    system: str | None         # already masked
    max_tokens: int
    pii_masked: int
    use_cache: bool
    cache_key: str | None


def to_converse_messages(messages: list[dict]) -> list[dict]:
    """Gateway format {"role", "content": "text"} -> Bedrock Converse format {"role", "content": [{"text"}]}."""
    return [{"role": m["role"], "content": [{"text": m["content"]}]} for m in messages]


def _log(req_or_none: ChatRequest | None, **fields: Any) -> UsageLog:
    if req_or_none is not None:
        fields.setdefault("department", req_or_none.department)
        fields.setdefault("api_key", req_or_none.api_key)
        fields.setdefault("model_id", req_or_none.price.model_id)
        fields.setdefault("pii_masked_count", req_or_none.pii_masked)
    return UsageLog.objects.create(**fields)


# ---------------------------------------------------------------- 1-4: checks before the model call

def prepare(api_key: ApiKey, data: dict) -> ChatRequest:
    department = api_key.department
    model_id = data["model"]

    price = ModelPrice.objects.filter(model_id=model_id, is_enabled=True).first()
    if price is None:
        raise GatewayError("model_not_allowed", f"Model '{model_id}' is not enabled on this gateway.", 400)

    messages, system, pii_masked = pii.mask_request(data["messages"], data.get("system") or "")

    status = budgets.budget_status(department)
    if status.blocked:
        _log(
            None,
            department=department,
            api_key=api_key,
            model_id=model_id,
            status=UsageLog.Status.BLOCKED,
            error_code="budget_exceeded",
            pii_masked_count=pii_masked,
            streamed=data["stream"],
        )
        raise GatewayError(
            "budget_exceeded",
            f"The monthly budget of '{department.name}' is used up "
            f"(${status.spend:.2f} of ${status.budget:.2f}). Ask an admin to raise it.",
            403,
        )

    converse_messages = to_converse_messages(messages)
    use_cache = data["cache"] and not data["stream"]
    return ChatRequest(
        api_key=api_key,
        department=department,
        price=price,
        messages=converse_messages,
        system=system or None,
        max_tokens=data["max_tokens"],
        pii_masked=pii_masked,
        use_cache=use_cache,
        cache_key=cache.make_key(department.id, model_id, system, converse_messages, data["max_tokens"]) if use_cache else None,
    )


# ---------------------------------------------------------------- helpers for 5-6

def _fallback_for(price: ModelPrice, exc: BedrockError) -> ModelPrice | None:
    if exc.http_status not in RETRYABLE_STATUSES or not price.fallback_model_id:
        return None
    return ModelPrice.objects.filter(model_id=price.fallback_model_id, is_enabled=True).first()


def _fail(req: ChatRequest, exc: BedrockError, streamed: bool) -> GatewayError:
    """Logs a failed model call and turns it into the error the calling app sees."""
    _log(req, status=UsageLog.Status.ERROR, error_code=exc.code, streamed=streamed)
    log.warning("model call failed dept=%s model=%s code=%s detail=%s", req.department.name, req.price.model_id, exc.code, exc)
    message = PUBLIC_ERROR_MESSAGES.get(exc.http_status, "The model provider returned an error.")
    return GatewayError(exc.code, message, exc.http_status)


def _result(log_row: UsageLog, req: ChatRequest, served: str, stop_reason: str, cost: Decimal) -> dict[str, Any]:
    return {
        "id": log_row.id,
        "model": req.price.model_id,
        "served_model": served,
        "fallback_used": log_row.fallback_used,
        "cached": log_row.cached,
        "stop_reason": stop_reason,
        "usage": {
            "input_tokens": log_row.input_tokens,
            "output_tokens": log_row.output_tokens,
            "cost_usd": str(cost),
        },
        "pii_masked": req.pii_masked,
        "latency_ms": log_row.latency_ms,
    }


# ---------------------------------------------------------------- normal (non-streaming) request

def run_chat(req: ChatRequest) -> dict[str, Any]:
    if req.use_cache:
        hit = cache.get_answer(req.cache_key)
        if hit:
            row = _log(req, status=UsageLog.Status.OK, served_model_id=hit["served_model"], cached=True)
            return {**_result(row, req, hit["served_model"], hit["stop_reason"], ZERO_COST), "content": hit["content"]}

    client = get_client()
    price, fallback_used = req.price, False
    call = dict(messages=req.messages, system=req.system, max_tokens=req.max_tokens)
    try:
        result = client.converse(model_id=price.model_id, **call)
    except BedrockError as exc:
        fallback = _fallback_for(price, exc)
        if fallback is None:
            raise _fail(req, exc, streamed=False) from exc
        log.warning("model %s failed (%s), trying fallback %s", price.model_id, exc.code, fallback.model_id)
        try:
            result = client.converse(model_id=fallback.model_id, **call)
        except BedrockError as exc2:
            raise _fail(req, exc2, streamed=False) from exc2
        price, fallback_used = fallback, True

    cost = price.cost(result.input_tokens, result.output_tokens)
    row = _log(
        req,
        status=UsageLog.Status.OK,
        served_model_id=price.model_id,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=cost,
        latency_ms=result.latency_ms,
        fallback_used=fallback_used,
    )
    if req.use_cache:
        cache.save_answer(req.cache_key, {"served_model": price.model_id, "content": result.text, "stop_reason": result.stop_reason})
    budgets.record_alerts(req.department)
    return {**_result(row, req, price.model_id, result.stop_reason, cost), "content": result.text}


# ---------------------------------------------------------------- streaming request

@dataclass
class OpenStream:
    events: Iterator[dict[str, Any]]
    price: ModelPrice           # the model that is answering
    fallback_used: bool


def _start(client, model_id: str, req: ChatRequest) -> Iterator[dict[str, Any]]:
    """Starts the stream and waits for its first event. Connection errors (throttling...) show up here,
    BEFORE anything is sent to the caller: the only moment a fallback or a real HTTP error code is still possible."""
    events = client.converse_stream(model_id=model_id, messages=req.messages, system=req.system, max_tokens=req.max_tokens)
    first = next(events, None)
    return iter(()) if first is None else itertools.chain([first], events)


def open_stream(req: ChatRequest) -> OpenStream:
    """Raises GatewayError (already logged) if neither the model nor its fallback could start."""
    client = get_client()
    try:
        return OpenStream(_start(client, req.price.model_id, req), req.price, False)
    except BedrockError as exc:
        fallback = _fallback_for(req.price, exc)
        if fallback is None:
            raise _fail(req, exc, streamed=True) from exc
        log.warning("model %s failed (%s), trying fallback %s", req.price.model_id, exc.code, fallback.model_id)
        try:
            return OpenStream(_start(client, fallback.model_id, req), fallback, True)
        except BedrockError as exc2:
            raise _fail(req, exc2, streamed=True) from exc2


def _sse(payload: dict[str, Any]) -> str:
    """One Server-Sent Event: a 'data:' line with JSON, then an empty line."""
    return f"data: {json.dumps(payload)}\n\n"


def stream_events(req: ChatRequest, stream: OpenStream) -> Iterator[str]:
    """Yields SSE events: {"type": "text"} pieces, then {"type": "done"} with usage + cost,
    or {"type": "error"} if the model fails halfway."""
    usage: dict[str, Any] = {"input_tokens": 0, "output_tokens": 0, "stop_reason": "", "latency_ms": 0}
    logged = False
    try:
        for event in stream.events:
            if event["type"] == "text":
                yield _sse({"type": "text", "text": event["text"]})
            elif event["type"] == "usage":
                usage = event
        logged = True  # (logged as OK below)
    except BedrockError as exc:
        logged = True
        error = _fail(req, exc, streamed=True)
        yield _sse({"type": "error", "error": {"code": error.error_code, "message": str(error.detail)}})
        return
    finally:
        if not logged:
            # The caller closed the connection halfway (GeneratorExit). Bedrock reports token counts only at
            # the end of the stream, so they are unknown here: the request is logged without cost.
            _log(
                req,
                status=UsageLog.Status.ERROR,
                error_code="client_disconnected",
                served_model_id=stream.price.model_id,
                streamed=True,
                fallback_used=stream.fallback_used,
            )

    cost = stream.price.cost(usage["input_tokens"], usage["output_tokens"])
    row = _log(
        req,
        status=UsageLog.Status.OK,
        served_model_id=stream.price.model_id,
        input_tokens=usage["input_tokens"],
        output_tokens=usage["output_tokens"],
        cost_usd=cost,
        latency_ms=usage["latency_ms"],
        streamed=True,
        fallback_used=stream.fallback_used,
    )
    budgets.record_alerts(req.department)
    yield _sse({"type": "done", **_result(row, req, stream.price.model_id, usage["stop_reason"], cost)})
