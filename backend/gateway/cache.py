"""Answer cache (Redis): the same request from the same department within GATEWAY_CACHE_TTL_SECONDS gets the
saved answer instead of a new model call (no cost, much faster).

- The key is a SHA-256 hash of (department, model, system prompt, messages, max_tokens), built AFTER masking,
  so personal data is never part of a key. Departments never share cached answers.
- Exact match only: a request with one different word is a different key (no "semantic" cache).
- Not used for streaming requests. A caller can skip it with "cache": false.
- If Redis is down, the gateway just calls the model ("fail open"): the cache only saves money,
  it must never stop requests.
- Cached answers are kept in Redis for the TTL only (in memory, not in the database).
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache

log = logging.getLogger("gateway")


def make_key(department_id: int, model_id: str, system: str, messages: list[dict], max_tokens: int) -> str:
    payload = json.dumps(
        {"department": department_id, "model": model_id, "system": system, "messages": messages, "max_tokens": max_tokens},
        sort_keys=True,
        ensure_ascii=False,
    )
    return "gw:answer:" + hashlib.sha256(payload.encode()).hexdigest()


def get_answer(key: str) -> dict[str, Any] | None:
    try:
        return cache.get(key)
    except Exception:
        log.warning("cache read failed, calling the model instead", exc_info=True)
        return None


def save_answer(key: str, value: dict[str, Any]) -> None:
    try:
        cache.set(key, value, timeout=settings.GATEWAY_CACHE_TTL_SECONDS)
    except Exception:
        log.warning("cache write failed", exc_info=True)
