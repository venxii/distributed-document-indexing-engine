import asyncio
import random
from collections.abc import Awaitable, Callable
from time import monotonic

import httpx

from app.crawler.rate_limiter import PerHostRateLimiter
from app.crawler.robots import RobotsTxtChecker
from app.crawler.types import CrawlerConfig, CrawlFailureReason, CrawlResult, RetryPolicy

SleepCallable = Callable[[float], Awaitable[None]]


class CrawlerService:
    """Fetches immutable external document snapshots politely and predictably."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        config: CrawlerConfig | None = None,
        robots_checker: RobotsTxtChecker | None = None,
        rate_limiter: PerHostRateLimiter | None = None,
        sleep: SleepCallable = asyncio.sleep,
    ) -> None:
        self._client = client
        self._config = config or CrawlerConfig()
        self._robots_checker = robots_checker or RobotsTxtChecker(
            client=client,
            user_agent=self._config.user_agent,
            timeout_seconds=self._config.request_timeout_seconds,
        )
        self._rate_limiter = rate_limiter or PerHostRateLimiter(
            delay_seconds=self._config.per_host_delay_seconds,
            sleep=sleep,
        )
        self._sleep = sleep

    async def fetch_snapshot(self, url: str) -> CrawlResult:
        started_at = monotonic()

        robots_decision = await self._robots_checker.is_allowed(url)
        if not robots_decision.allowed:
            return self._failure_result(
                url=url,
                started_at=started_at,
                attempts=0,
                reason=CrawlFailureReason.blocked_by_robots,
                error_message=robots_decision.reason,
            )

        return await self._fetch_with_retries(url=url, started_at=started_at)

    async def _fetch_with_retries(self, url: str, started_at: float) -> CrawlResult:
        retry_policy = self._config.retry_policy
        last_result: CrawlResult | None = None

        for attempt in range(1, retry_policy.max_attempts + 1):
            await self._rate_limiter.wait_for_turn(url)
            result = await self._fetch_once(url=url, started_at=started_at, attempt=attempt)

            if result.succeeded or not self._should_retry(result):
                return result

            last_result = result
            if attempt < retry_policy.max_attempts:
                await self._sleep(self._backoff_seconds(retry_policy, attempt))

        if last_result is None:
            return self._failure_result(
                url=url,
                started_at=started_at,
                attempts=0,
                reason=CrawlFailureReason.unexpected_error,
                error_message="crawler exited without making an attempt",
            )
        return last_result

    async def _fetch_once(self, url: str, started_at: float, attempt: int) -> CrawlResult:
        try:
            response = await self._client.get(
                url,
                headers={"User-Agent": self._config.user_agent},
                timeout=self._config.request_timeout_seconds,
                follow_redirects=True,
            )
        except httpx.TimeoutException as exc:
            return self._failure_result(
                url=url,
                started_at=started_at,
                attempts=attempt,
                reason=CrawlFailureReason.timeout,
                error_message=str(exc) or exc.__class__.__name__,
            )
        except httpx.TooManyRedirects as exc:
            return self._failure_result(
                url=url,
                started_at=started_at,
                attempts=attempt,
                reason=CrawlFailureReason.too_many_redirects,
                error_message=str(exc) or exc.__class__.__name__,
            )
        except httpx.NetworkError as exc:
            return self._failure_result(
                url=url,
                started_at=started_at,
                attempts=attempt,
                reason=CrawlFailureReason.network_error,
                error_message=str(exc) or exc.__class__.__name__,
            )
        except httpx.HTTPError as exc:
            return self._failure_result(
                url=url,
                started_at=started_at,
                attempts=attempt,
                reason=CrawlFailureReason.network_error,
                error_message=str(exc) or exc.__class__.__name__,
            )
        content = response.content
        if 200 <= response.status_code < 300:
            return CrawlResult(
                url=url,
                final_url=str(response.url),
                status_code=response.status_code,
                content=content,
                content_type=response.headers.get("content-type"),
                fetched_bytes=len(content),
                duration_ms=self._elapsed_ms(started_at),
                attempts=attempt,
                failure_reason=None,
                error_message=None,
            )

        reason = (
            CrawlFailureReason.server_error
            if response.status_code >= 500 or response.status_code == 429
            else CrawlFailureReason.client_error
        )
        return CrawlResult(
            url=url,
            final_url=str(response.url),
            status_code=response.status_code,
            content=None,
            content_type=response.headers.get("content-type"),
            fetched_bytes=len(content),
            duration_ms=self._elapsed_ms(started_at),
            attempts=attempt,
            failure_reason=reason,
            error_message=f"HTTP {response.status_code}",
        )

    @staticmethod
    def _should_retry(result: CrawlResult) -> bool:
        return result.failure_reason in {
            CrawlFailureReason.timeout,
            CrawlFailureReason.network_error,
            CrawlFailureReason.server_error,
        }

    @staticmethod
    def _backoff_seconds(retry_policy: RetryPolicy, attempt: int) -> float:
        base_delay = retry_policy.base_backoff_seconds * (2 ** (attempt - 1))
        capped_delay = min(base_delay, retry_policy.max_backoff_seconds)
        if retry_policy.jitter_ratio == 0 or capped_delay == 0:
            return capped_delay

        jitter = capped_delay * retry_policy.jitter_ratio
        return random.uniform(capped_delay - jitter, capped_delay + jitter)

    def _failure_result(
        self,
        url: str,
        started_at: float,
        attempts: int,
        reason: CrawlFailureReason,
        error_message: str | None,
    ) -> CrawlResult:
        return CrawlResult(
            url=url,
            final_url=None,
            status_code=None,
            content=None,
            content_type=None,
            fetched_bytes=0,
            duration_ms=self._elapsed_ms(started_at),
            attempts=attempts,
            failure_reason=reason,
            error_message=error_message,
        )

    @staticmethod
    def _elapsed_ms(started_at: float) -> int:
        return int((monotonic() - started_at) * 1000)
