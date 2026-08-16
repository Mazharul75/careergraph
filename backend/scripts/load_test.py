"""A small, dependency-free load test against a running CareerGraph API.

Not a benchmark suite — a smoke-level answer to the question every deployment eventually gets
asked: "what happens when more than one person uses it?" It measures request latency under
modest concurrency for the endpoints a real session touches, and prints p50/p95/p99.

Deliberately gentle with auth: it registers ONE throwaway user and logs in ONCE, then reuses
the access token — both endpoints are rate-limited (ADR-0011), and a load test that trips its
own rate limiter is measuring the limiter, not the API.

Usage (stack must be up):
    uv run python scripts/load_test.py \
        [--base-url http://localhost:8000] [--requests 200] [--concurrency 10]
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
import time
import uuid

import httpx


def percentile(samples: list[float], pct: float) -> float:
    """Nearest-rank percentile; good enough at these sample sizes."""
    ordered = sorted(samples)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * len(ordered)) - 1))
    return ordered[index]


async def hammer(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    requests: int,
    concurrency: int,
    headers: dict[str, str] | None = None,
) -> tuple[list[float], int]:
    """Fire `requests` calls with at most `concurrency` in flight; return latencies + errors."""
    semaphore = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    errors = 0

    async def one() -> None:
        nonlocal errors
        async with semaphore:
            start = time.perf_counter()
            try:
                response = await client.request(method, url, headers=headers)
                if response.status_code >= 400:
                    errors += 1
                    return
            except httpx.HTTPError:
                errors += 1
                return
            latencies.append((time.perf_counter() - start) * 1000)

    await asyncio.gather(*(one() for _ in range(requests)))
    return latencies, errors


def report(name: str, latencies: list[float], errors: int, wall_seconds: float) -> None:
    if not latencies:
        print(f"{name:32s}  ALL {errors} REQUESTS FAILED")
        return
    print(
        f"{name:32s}  n={len(latencies):4d}  err={errors:3d}  "
        f"rps={len(latencies) / wall_seconds:6.1f}  "
        f"p50={percentile(latencies, 50):7.1f}ms  "
        f"p95={percentile(latencies, 95):7.1f}ms  "
        f"p99={percentile(latencies, 99):7.1f}ms  "
        f"mean={statistics.fmean(latencies):7.1f}ms"
    )


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.base_url, timeout=30.0) as client:
        health = await client.get("/health")
        if health.status_code != 200:
            print(f"API at {args.base_url} is not healthy: {health.status_code}", file=sys.stderr)
            return 1

        # One throwaway account, one login — see the module docstring.
        email = f"loadtest-{uuid.uuid4().hex[:10]}@example.com"
        # Not a secret: the account exists for the lifetime of one benchmark run against a
        # developer's own stack.
        password = "LoadTest-Passw0rd-For-Benchmarks"  # noqa: S105
        registered = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "full_name": "Load Test"},
        )
        if registered.status_code != 201:
            print(f"registration failed: {registered.status_code} {registered.text}")
            return 1
        login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
        token = login.json()["access_token"]
        auth = {"Authorization": f"Bearer {token}"}

        print(f"target={args.base_url}  requests={args.requests}  concurrency={args.concurrency}\n")

        scenarios: list[tuple[str, str, str, dict[str, str] | None]] = [
            # Unauthenticated, no DB: the floor — pure framework + middleware overhead.
            ("GET /health (no db)", "GET", "/health", None),
            # Readiness touches Postgres and Redis: the cost of one trivial query.
            ("GET /health/ready (db+redis)", "GET", "/health/ready", None),
            # The authenticated list endpoints a dashboard session actually hits: JWT
            # verification + repository query + Pydantic serialisation.
            ("GET /api/v1/jobs (auth)", "GET", "/api/v1/jobs", auth),
            ("GET /api/v1/skills/me (auth)", "GET", "/api/v1/skills/me", auth),
            ("GET /api/v1/resumes (auth)", "GET", "/api/v1/resumes", auth),
        ]

        for name, method, url, headers in scenarios:
            start = time.perf_counter()
            latencies, errors = await hammer(
                client,
                method,
                url,
                requests=args.requests,
                concurrency=args.concurrency,
                headers=headers,
            )
            report(name, latencies, errors, time.perf_counter() - start)

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
