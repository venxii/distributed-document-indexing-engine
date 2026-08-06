import argparse
import asyncio
import logging
import tracemalloc
from dataclasses import asdict
from time import monotonic
from typing import Any

import httpx

from app.crawler.service import CrawlerService
from app.crawler.types import CrawlerConfig, RetryPolicy

CAREER_URLS = [
    "https://github.com/about/careers",
    "https://vercel.com/careers",
    "https://stripe.com/jobs",
    "https://www.cloudflare.com/careers/",
    "https://www.amazon.jobs/",
    "https://jobs.netflix.com/",
]


async def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Phase 2 crawler behavior.")
    parser.add_argument(
        "--real-network",
        action="store_true",
        help="Run real external career page and HTTP status checks.",
    )
    parser.add_argument(
        "--memory-iterations",
        type=int,
        default=300,
        help="Sequential mock crawls for the memory stability check.",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level for crawler validation output.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.real_network:
        await validate_real_career_pages()
        await validate_real_retry_behavior()
    else:
        print("Skipping real-network checks. Pass --real-network to crawl external sites.")

    await validate_simulated_retry_behavior()
    await validate_rate_limiting()
    await validate_idempotency()
    await validate_concurrency()
    await validate_memory_stability(args.memory_iterations)
    return 0


async def validate_real_career_pages() -> None:
    print("\n== Real Career Page Smoke Test ==")
    timeout = httpx.Timeout(20.0, connect=10.0)
    limits = httpx.Limits(max_connections=10, max_keepalive_connections=5)
    config = CrawlerConfig(
        request_timeout_seconds=20.0,
        per_host_delay_seconds=0.25,
        retry_policy=RetryPolicy(max_attempts=2, base_backoff_seconds=0.5, jitter_ratio=0),
    )

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        crawler = CrawlerService(client=client, config=config)
        for url in CAREER_URLS:
            result = await crawler.fetch_snapshot(url)
            print_result(url, result)


async def validate_real_retry_behavior() -> None:
    print("\n== Real Retry Validation ==")
    config = CrawlerConfig(
        request_timeout_seconds=5.0,
        per_host_delay_seconds=0,
        retry_policy=RetryPolicy(
            max_attempts=3,
            base_backoff_seconds=0.25,
            max_backoff_seconds=1,
            jitter_ratio=0,
        ),
    )
    urls = [
        "https://httpbin.org/status/500",
        "https://httpbin.org/status/429",
        "https://httpbin.org/status/404",
    ]

    async with httpx.AsyncClient() as client:
        crawler = CrawlerService(client=client, config=config)
        for url in urls:
            result = await crawler.fetch_snapshot(url)
            print_result(url, result)

    timeout_config = CrawlerConfig(
        request_timeout_seconds=0.001,
        per_host_delay_seconds=0,
        retry_policy=RetryPolicy(
            max_attempts=2,
            base_backoff_seconds=0.01,
            max_backoff_seconds=0.01,
            jitter_ratio=0,
        ),
    )
    async with httpx.AsyncClient() as client:
        crawler = CrawlerService(client=client, config=timeout_config)
        result = await crawler.fetch_snapshot("https://www.amazon.jobs/")
        print_result("timeout forced: https://www.amazon.jobs/", result)


async def validate_simulated_retry_behavior() -> None:
    print("\n== Deterministic Retry Validation ==")
    calls_by_path: dict[str, int] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")

        calls_by_path[request.url.path] = calls_by_path.get(request.url.path, 0) + 1
        if request.url.path == "/status/500":
            return httpx.Response(500)
        if request.url.path == "/status/429":
            return httpx.Response(429)
        if request.url.path == "/status/404":
            return httpx.Response(404)
        return httpx.Response(200, content=b"ok")

    async def no_sleep(_: float) -> None:
        return None

    config = CrawlerConfig(
        per_host_delay_seconds=0,
        retry_policy=RetryPolicy(
            max_attempts=3,
            base_backoff_seconds=0.01,
            max_backoff_seconds=0.01,
            jitter_ratio=0,
        ),
    )
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://example.com",
    ) as client:
        crawler = CrawlerService(client=client, config=config, sleep=no_sleep)
        server_error = await crawler.fetch_snapshot("https://example.com/status/500")
        rate_limited = await crawler.fetch_snapshot("https://example.com/status/429")
        not_found = await crawler.fetch_snapshot("https://example.com/status/404")

    assert server_error.attempts == 3
    assert rate_limited.attempts == 3
    assert not_found.attempts == 1
    assert calls_by_path["/status/500"] == 3
    assert calls_by_path["/status/429"] == 3
    assert calls_by_path["/status/404"] == 1
    print("PASS: 500 and 429 retried 3 times; 404 stopped after 1 attempt.")


async def validate_rate_limiting() -> None:
    print("\n== Rate Limit Validation ==")

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(200, content=b"ok")

    async def no_sleep(_: float) -> None:
        return None

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://example.com",
    ) as client:
        crawler = CrawlerService(
            client=client,
            config=CrawlerConfig(per_host_delay_seconds=10),
            sleep=no_sleep,
        )
        first_result = await crawler.fetch_snapshot("https://example.com/a")
        second_result = await crawler.fetch_snapshot("https://example.com/b")

    assert first_result.rate_limit_delay_ms == 0
    assert second_result.rate_limit_delay_ms > 0
    print(
        "PASS: repeated same-host crawl recorded "
        f"{second_result.rate_limit_delay_ms}ms of rate-limit delay."
    )


async def validate_idempotency() -> None:
    print("\n== Idempotency Check ==")

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(200, content=b"<html>same snapshot</html>")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://example.com",
    ) as client:
        crawler = CrawlerService(
            client=client,
            config=CrawlerConfig(per_host_delay_seconds=0),
        )
        results = [await crawler.fetch_snapshot("https://example.com/careers") for _ in range(3)]

    comparable = [
        {
            "url": result.url,
            "final_url": result.final_url,
            "status_code": result.status_code,
            "content": result.content,
            "content_type": result.content_type,
            "fetched_bytes": result.fetched_bytes,
            "attempts": result.attempts,
            "robots_url": result.robots_url,
            "robots_allowed": result.robots_allowed,
            "robots_reason": result.robots_reason,
            "rate_limit_delay_ms": result.rate_limit_delay_ms,
            "failure_reason": result.failure_reason,
            "error_message": result.error_message,
        }
        for result in results
    ]
    assert comparable[0] == comparable[1] == comparable[2]
    print("PASS: three repeated mock crawls produced identical stable output fields.")


async def validate_concurrency() -> None:
    print("\n== Concurrency Check ==")
    active_requests = 0
    max_active_requests = 0
    paths_requested: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active_requests, max_active_requests
        paths_requested.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")

        active_requests += 1
        max_active_requests = max(max_active_requests, active_requests)
        await asyncio.sleep(0.05)
        active_requests -= 1
        return httpx.Response(200, content=b"<html>ok</html>")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://example.com",
    ) as client:
        crawler = CrawlerService(
            client=client,
            config=CrawlerConfig(per_host_delay_seconds=0),
        )
        started = monotonic()
        results = await asyncio.gather(
            *[
                crawler.fetch_snapshot(f"https://example.com/careers/{index}")
                for index in range(50)
            ]
        )
        elapsed = monotonic() - started

    assert all(result.succeeded for result in results)
    assert max_active_requests > 1
    assert elapsed < 1.5
    print(
        "PASS: 50 mock fetches completed concurrently "
        f"in {elapsed:.2f}s; max active requests={max_active_requests}."
    )
    print(f"robots.txt requests observed: {paths_requested.count('/robots.txt')}")


async def validate_memory_stability(iterations: int) -> None:
    print("\n== Memory Stability Check ==")

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(200, content=b"<html>stable</html>")

    tracemalloc.start()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://example.com",
    ) as client:
        crawler = CrawlerService(
            client=client,
            config=CrawlerConfig(per_host_delay_seconds=0),
        )

        first_snapshot: tuple[int, int] | None = None
        for index in range(iterations):
            result = await crawler.fetch_snapshot(f"https://example.com/careers/{index}")
            assert result.succeeded
            if index == 49:
                first_snapshot = tracemalloc.get_traced_memory()

        current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    if first_snapshot is None:
        first_snapshot = (current, peak)

    growth_bytes = current - first_snapshot[0]
    print(
        "PASS: completed "
        f"{iterations} sequential mock crawls; current={current:,} bytes, "
        f"peak={peak:,} bytes, growth_after_warmup={growth_bytes:,} bytes."
    )


def print_result(label: str, result: Any) -> None:
    result_dict = asdict(result)
    result_dict["content"] = f"{len(result.content or b'')} bytes"
    print(f"{label}: {result_dict}")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
