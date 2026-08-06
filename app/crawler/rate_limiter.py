import asyncio
from collections.abc import Awaitable, Callable
from time import monotonic
from urllib.parse import urlsplit

SleepCallable = Callable[[float], Awaitable[None]]


class PerHostRateLimiter:
    """Enforces a minimum delay between requests to the same host."""

    def __init__(
        self,
        delay_seconds: float,
        sleep: SleepCallable = asyncio.sleep,
    ) -> None:
        if delay_seconds < 0:
            raise ValueError("delay_seconds must be non-negative")
        self._delay_seconds = delay_seconds
        self._sleep = sleep
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_request_at: dict[str, float] = {}

    async def wait_for_turn(self, url: str) -> None:
        host_key = self._host_key(url)
        lock = self._locks.setdefault(host_key, asyncio.Lock())

        async with lock:
            last_request_at = self._last_request_at.get(host_key)
            now = monotonic()
            if last_request_at is not None:
                elapsed = now - last_request_at
                remaining_delay = self._delay_seconds - elapsed
                if remaining_delay > 0:
                    await self._sleep(remaining_delay)
            self._last_request_at[host_key] = monotonic()

    @staticmethod
    def _host_key(url: str) -> str:
        parsed = urlsplit(url)
        return f"{parsed.scheme.lower()}://{(parsed.netloc or parsed.path).lower()}"

