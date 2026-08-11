import argparse
import asyncio
import logging

import httpx

from app.crawler.service import CrawlerService
from app.crawler.types import CrawlerConfig, RetryPolicy
from app.parser.html import HtmlDocumentParser

CAREER_URLS = [
    "https://github.com/about/careers",
    "https://vercel.com/careers",
    "https://stripe.com/jobs",
    "https://www.cloudflare.com/careers/",
    "https://www.amazon.jobs/",
    "https://jobs.netflix.com/",
]


async def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Phase 3 parser behavior.")
    parser.add_argument(
        "--real-network",
        action="store_true",
        help="Fetch and parse real external career pages.",
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level for parser validation output.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)

    validate_static_html()

    if args.real_network:
        await validate_real_pages()
    else:
        print("Skipping real-network checks. Pass --real-network to fetch external pages.")

    return 0


def validate_static_html() -> None:
    print("\n== Static Parser Validation ==")
    html = """
    <html>
      <head>
        <title>Example Careers</title>
        <link rel="canonical" href="/careers">
      </head>
      <body>
        <main>
          <h1>Example Careers</h1>
          <p>Build reliable indexing systems with a small backend team.</p>
        </main>
      </body>
    </html>
    """
    result = HtmlDocumentParser().parse(
        html,
        source_url="https://example.com/jobs",
        final_url="https://example.com/jobs",
        content_type="text/html",
    )
    assert result.succeeded
    assert result.document is not None
    assert result.document.canonical_url == "https://example.com/careers"
    assert "reliable indexing systems" in result.document.normalized_text
    print("PASS: static HTML normalized into the internal document schema.")


async def validate_real_pages() -> None:
    print("\n== Real Career Page Parser Smoke Test ==")
    crawler_config = CrawlerConfig(
        request_timeout_seconds=20.0,
        per_host_delay_seconds=0.25,
        retry_policy=RetryPolicy(max_attempts=2, base_backoff_seconds=0.5, jitter_ratio=0),
    )
    parser = HtmlDocumentParser()

    async with httpx.AsyncClient() as client:
        crawler = CrawlerService(client=client, config=crawler_config)
        for url in CAREER_URLS:
            crawl_result = await crawler.fetch_snapshot(url)
            if not crawl_result.succeeded or crawl_result.content is None:
                print(f"{url}: CRAWL FAILED {crawl_result.failure_reason}")
                continue

            parse_result = parser.parse(
                crawl_result.content,
                source_url=url,
                final_url=crawl_result.final_url,
                content_type=crawl_result.content_type,
            )
            if not parse_result.succeeded or parse_result.document is None:
                print(f"{url}: PARSE FAILED {parse_result.failure_reason}")
                continue

            document = parse_result.document
            print(
                f"{url}: title={document.title!r}, "
                f"canonical={document.canonical_url!r}, "
                f"text_length={len(document.normalized_text)}, "
                f"headings={len(document.headings)}"
            )


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

