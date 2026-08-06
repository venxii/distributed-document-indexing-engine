import httpx
import pytest

from app.crawler.rate_limiter import PerHostRateLimiter
from app.crawler.service import CrawlerService
from app.crawler.types import CrawlerConfig, CrawlFailureReason, RetryPolicy


async def no_sleep(_: float) -> None:
    return None


@pytest.mark.asyncio
async def test_fetch_snapshot_success() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /\n")
        return httpx.Response(
            200,
            content=b"<html>careers</html>",
            headers={"content-type": "text/html"},
        )

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://example.com",
    ) as client:
        crawler = CrawlerService(
            client=client,
            config=CrawlerConfig(per_host_delay_seconds=0),
            sleep=no_sleep,
        )

        result = await crawler.fetch_snapshot("https://example.com/careers")

    assert result.succeeded
    assert result.status_code == 200
    assert result.content == b"<html>careers</html>"
    assert result.content_type == "text/html"
    assert result.fetched_bytes == len(b"<html>careers</html>")
    assert result.attempts == 1


@pytest.mark.asyncio
async def test_fetch_snapshot_respects_robots_txt() -> None:
    requested_paths: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /careers\n")
        return httpx.Response(200, content=b"should not be fetched")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://example.com",
    ) as client:
        crawler = CrawlerService(
            client=client,
            config=CrawlerConfig(per_host_delay_seconds=0),
            sleep=no_sleep,
        )

        result = await crawler.fetch_snapshot("https://example.com/careers")

    assert not result.succeeded
    assert result.failure_reason == CrawlFailureReason.blocked_by_robots
    assert result.attempts == 0
    assert requested_paths == ["/robots.txt"]


@pytest.mark.asyncio
async def test_fetch_snapshot_retries_retryable_server_errors() -> None:
    attempts = 0
    slept_for: list[float] = []

    async def capture_sleep(delay: float) -> None:
        slept_for.append(delay)

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path == "/robots.txt":
            return httpx.Response(404)

        attempts += 1
        if attempts == 1:
            return httpx.Response(503, content=b"try again")
        return httpx.Response(200, content=b"ok")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://example.com",
    ) as client:
        crawler = CrawlerService(
            client=client,
            config=CrawlerConfig(
                per_host_delay_seconds=0,
                retry_policy=RetryPolicy(
                    max_attempts=3,
                    base_backoff_seconds=0.25,
                    max_backoff_seconds=1,
                    jitter_ratio=0,
                ),
            ),
            sleep=capture_sleep,
        )

        result = await crawler.fetch_snapshot("https://example.com/careers")

    assert result.succeeded
    assert result.content == b"ok"
    assert result.attempts == 2
    assert attempts == 2
    assert slept_for == [0.25]


@pytest.mark.asyncio
async def test_fetch_snapshot_does_not_retry_regular_client_errors() -> None:
    attempts = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path == "/robots.txt":
            return httpx.Response(404)

        attempts += 1
        return httpx.Response(404, content=b"missing")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://example.com",
    ) as client:
        crawler = CrawlerService(
            client=client,
            config=CrawlerConfig(per_host_delay_seconds=0),
            sleep=no_sleep,
        )

        result = await crawler.fetch_snapshot("https://example.com/missing")

    assert not result.succeeded
    assert result.failure_reason == CrawlFailureReason.client_error
    assert result.attempts == 1
    assert attempts == 1


@pytest.mark.asyncio
async def test_per_host_rate_limiter_delays_repeated_requests_to_same_host() -> None:
    slept_for: list[float] = []

    async def capture_sleep(delay: float) -> None:
        slept_for.append(delay)

    limiter = PerHostRateLimiter(delay_seconds=10, sleep=capture_sleep)

    await limiter.wait_for_turn("https://example.com/a")
    await limiter.wait_for_turn("https://example.com/b")
    await limiter.wait_for_turn("https://other.example.com/a")

    assert len(slept_for) == 1
    assert 0 < slept_for[0] <= 10
