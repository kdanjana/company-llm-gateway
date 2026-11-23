"""Measures how much time the gateway itself adds to each request (its "overhead").

Uses only the Python standard library, so it runs on the laptop without installing anything.

1. Put the backend in fake mode (no AWS calls, no cost): in .env set
       GATEWAY_FAKE_BEDROCK=true      (DJANGO_DEBUG must be true)
   then:  docker compose -f docker-compose.dev.yml restart backend
2. Allow the fake model and create a key for a test department:
       docker compose -f docker-compose.dev.yml exec backend python manage.py set_model_price fake-model --input 0 --output 0
       docker compose -f docker-compose.dev.yml exec backend python manage.py create_department_key LoadTest
3. Run:
       python scripts/load_test.py --key gw_... --model fake-model --requests 500 --concurrency 10
4. Set GATEWAY_FAKE_BEDROCK=false again and restart the backend.

overhead = total time the client waited - time the (fake) model took (latency_ms in the answer).
The cache is switched off, so every request runs the full path: key check, masking, budget check, logging.
Note: Django's development server (runserver) is slower than a production server (e.g. gunicorn),
so treat the numbers as an upper bound.
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def one_request(url: str, key: str, model: str, number: int) -> tuple[float, float, str | None]:
    """Returns (total ms, model ms, error or None)."""
    body = json.dumps(
        {
            "model": model,
            "max_tokens": 50,
            "cache": False,
            # Contains an email, so the masking step does real work.
            "messages": [{"role": "user", "content": f"Load test {number}: reply to test{number}@example.com"}],
        }
    ).encode()
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read())
        return (time.perf_counter() - start) * 1000, float(data.get("latency_ms", 0)), None
    except urllib.error.HTTPError as exc:
        return (time.perf_counter() - start) * 1000, 0.0, f"HTTP {exc.code}"
    except Exception as exc:  # connection refused, timeout...
        return (time.perf_counter() - start) * 1000, 0.0, type(exc).__name__


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round(p / 100 * (len(ordered) - 1))))
    return ordered[index]


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure the LLM gateway's overhead per request.")
    parser.add_argument("--url", default="http://localhost:8000/api/v1/chat")
    parser.add_argument("--key", required=True, help="API key of a test department")
    parser.add_argument("--model", default="fake-model")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()

    # Warm-up: first requests open DB connections and load code; they would distort the numbers.
    for i in range(5):
        one_request(args.url, args.key, args.model, -i)

    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(lambda n: one_request(args.url, args.key, args.model, n), range(args.requests)))
    elapsed = time.perf_counter() - started

    ok = [(total, model) for total, model, error in results if error is None]
    errors: dict[str, int] = {}
    for _, _, error in results:
        if error:
            errors[error] = errors.get(error, 0) + 1

    print(f"\n{args.requests} requests, {args.concurrency} at a time, {elapsed:.1f} s  ->  {len(results) / elapsed:.1f} requests/s")
    if errors:
        print(f"errors: {errors}")
    if not ok:
        print("No successful requests: check the key, the model price row and that the backend is running.")
        return

    totals = [total for total, _ in ok]
    overheads = [max(0.0, total - model) for total, model in ok]
    print(f"{'':22}{'p50':>8}{'p95':>8}{'mean':>8}   (ms)")
    print(f"{'total time':22}{percentile(totals, 50):8.1f}{percentile(totals, 95):8.1f}{statistics.mean(totals):8.1f}")
    print(f"{'gateway overhead':22}{percentile(overheads, 50):8.1f}{percentile(overheads, 95):8.1f}{statistics.mean(overheads):8.1f}")


if __name__ == "__main__":
    main()
