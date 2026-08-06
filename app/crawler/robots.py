import logging
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RobotsDecision:
    allowed: bool
    robots_url: str
    reason: str | None = None


class RobotsTxtChecker:
    """Checks robots.txt rules and caches one parser per scheme/host."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        user_agent: str,
        timeout_seconds: float,
    ) -> None:
        self._client = client
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._parsers: dict[str, RobotFileParser | None] = {}

    async def is_allowed(self, url: str) -> RobotsDecision:
        site_root = self._site_root(url)
        robots_url = urljoin(site_root, "/robots.txt")

        if site_root not in self._parsers:
            logger.info("crawler.robots_fetch_started", extra={"robots_url": robots_url})
            self._parsers[site_root] = await self._fetch_parser(robots_url)

        parser = self._parsers[site_root]
        if parser is None:
            logger.warning("crawler.robots_unavailable", extra={"robots_url": robots_url})
            return RobotsDecision(
                allowed=True,
                robots_url=robots_url,
                reason="robots.txt unavailable; fail open",
            )

        allowed = parser.can_fetch(self._user_agent, url)
        reason = None if allowed else "robots.txt disallows this URL"
        logger.info(
            "crawler.robots_checked",
            extra={"url": url, "robots_url": robots_url, "allowed": allowed},
        )
        return RobotsDecision(allowed=allowed, robots_url=robots_url, reason=reason)

    async def _fetch_parser(self, robots_url: str) -> RobotFileParser | None:
        try:
            response = await self._client.get(robots_url, timeout=self._timeout_seconds)
        except httpx.HTTPError:
            return None

        if response.status_code >= 400:
            return None

        parser = RobotFileParser()
        parser.set_url(robots_url)
        parser.parse(response.text.splitlines())
        return parser

    @staticmethod
    def _site_root(url: str) -> str:
        parsed = urlsplit(url)
        return f"{parsed.scheme}://{parsed.netloc}"
