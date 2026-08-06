from dataclasses import dataclass
from enum import Enum


class CrawlFailureReason(str, Enum):
    blocked_by_robots = "blocked_by_robots"
    client_error = "client_error"
    server_error = "server_error"
    timeout = "timeout"
    network_error = "network_error"
    too_many_redirects = "too_many_redirects"
    unexpected_error = "unexpected_error"


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_backoff_seconds: float = 0.5
    max_backoff_seconds: float = 8.0
    jitter_ratio: float = 0.1

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.base_backoff_seconds < 0:
            raise ValueError("base_backoff_seconds must be non-negative")
        if self.max_backoff_seconds < self.base_backoff_seconds:
            raise ValueError("max_backoff_seconds must be >= base_backoff_seconds")
        if self.jitter_ratio < 0:
            raise ValueError("jitter_ratio must be non-negative")


@dataclass(frozen=True)
class CrawlerConfig:
    user_agent: str = "incremental-document-indexer/0.1"
    request_timeout_seconds: float = 10.0
    per_host_delay_seconds: float = 1.0
    retry_policy: RetryPolicy = RetryPolicy()


@dataclass(frozen=True)
class CrawlResult:
    url: str
    final_url: str | None
    status_code: int | None
    content: bytes | None
    content_type: str | None
    fetched_bytes: int
    duration_ms: int
    attempts: int
    robots_url: str | None
    robots_allowed: bool | None
    robots_reason: str | None
    rate_limit_delay_ms: int
    failure_reason: CrawlFailureReason | None
    error_message: str | None

    @property
    def succeeded(self) -> bool:
        return self.failure_reason is None and self.content is not None
