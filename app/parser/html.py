import logging
import re
from collections.abc import Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from app.parser.types import ParsedDocument, ParseFailureReason, ParserConfig, ParseResult

logger = logging.getLogger(__name__)

HTML_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
}
REMOVED_TAGS = {
    "script",
    "style",
    "noscript",
    "template",
    "svg",
    "canvas",
    "iframe",
}
BLOCK_TAGS = {
    "article",
    "aside",
    "div",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "section",
    "table",
    "td",
    "th",
    "tr",
    "ul",
}
WHITESPACE_RE = re.compile(r"\s+")
BLANK_LINES_RE = re.compile(r"\n{3,}")


class HtmlDocumentParser:
    """Converts raw HTML snapshots into a stable internal document shape."""

    def __init__(self, config: ParserConfig | None = None) -> None:
        self._config = config or ParserConfig()

    def parse(
        self,
        content: bytes | str,
        source_url: str,
        final_url: str | None = None,
        content_type: str | None = None,
    ) -> ParseResult:
        resolved_final_url = final_url or source_url
        if not content:
            return self._failure(ParseFailureReason.empty_content, "empty HTML content")

        if content_type is not None and not self._is_html_content_type(content_type):
            return self._failure(
                ParseFailureReason.non_html_content,
                f"unsupported content type: {content_type}",
            )

        soup = BeautifulSoup(content, "html.parser")
        self._remove_non_content_tags(soup)

        canonical_url = self._extract_canonical_url(soup, resolved_final_url)
        title = self._extract_title(soup)
        headings = tuple(self._extract_headings(soup))
        normalized_text = self._extract_normalized_text(soup)

        if len(normalized_text) < self._config.min_text_length:
            logger.warning(
                "parser.no_meaningful_text",
                extra={
                    "source_url": source_url,
                    "final_url": resolved_final_url,
                    "text_length": len(normalized_text),
                },
            )
            return self._failure(
                ParseFailureReason.no_meaningful_text,
                "parsed HTML did not contain enough meaningful text",
            )

        document = ParsedDocument(
            source_url=source_url,
            final_url=resolved_final_url,
            canonical_url=canonical_url,
            title=title,
            normalized_text=normalized_text,
            headings=headings,
        )
        logger.info(
            "parser.parse_succeeded",
            extra={
                "source_url": source_url,
                "final_url": resolved_final_url,
                "canonical_url": canonical_url,
                "text_length": len(normalized_text),
                "heading_count": len(headings),
            },
        )
        return ParseResult(document=document, failure_reason=None, error_message=None)

    @staticmethod
    def _is_html_content_type(content_type: str) -> bool:
        media_type = content_type.split(";", maxsplit=1)[0].strip().lower()
        return media_type in HTML_CONTENT_TYPES

    @staticmethod
    def _remove_non_content_tags(soup: BeautifulSoup) -> None:
        for tag in soup.find_all(REMOVED_TAGS):
            tag.decompose()

    @staticmethod
    def _extract_canonical_url(soup: BeautifulSoup, fallback_url: str) -> str:
        canonical = soup.find("link", rel=lambda value: value and "canonical" in value)
        if isinstance(canonical, Tag):
            href = canonical.get("href")
            if isinstance(href, str) and href.strip():
                return urljoin(fallback_url, href.strip())
        return fallback_url

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> str | None:
        for selector in (
            ('meta[property="og:title"]', "content"),
            ('meta[name="twitter:title"]', "content"),
        ):
            tag = soup.select_one(selector[0])
            if isinstance(tag, Tag):
                value = tag.get(selector[1])
                if isinstance(value, str) and value.strip():
                    return normalize_inline_text(value)

        if soup.title is not None and soup.title.string:
            return normalize_inline_text(soup.title.string)

        h1 = soup.find("h1")
        if h1 is not None:
            title = normalize_inline_text(h1.get_text(" ", strip=True))
            if title:
                return title
        return None

    @staticmethod
    def _extract_headings(soup: BeautifulSoup) -> Iterable[str]:
        seen: set[str] = set()
        for heading in soup.find_all(["h1", "h2", "h3"]):
            text = normalize_inline_text(heading.get_text(" ", strip=True))
            if text and text not in seen:
                seen.add(text)
                yield text

    @staticmethod
    def _extract_normalized_text(soup: BeautifulSoup) -> str:
        root = soup.find("main") or soup.find("article") or soup.body or soup
        if not isinstance(root, Tag):
            root = soup

        parts: list[str] = []
        for element in root.find_all(BLOCK_TAGS):
            if not isinstance(element, Tag) or HtmlDocumentParser._has_block_child(element):
                continue

            text = normalize_inline_text(element.get_text(" ", strip=True))
            if text:
                parts.append(text)

        if not parts:
            fallback_text = normalize_inline_text(root.get_text(" ", strip=True))
            if fallback_text:
                parts.append(fallback_text)

        return normalize_document_text("\n".join(parts))

    @staticmethod
    def _has_block_child(tag: Tag) -> bool:
        return tag.find(BLOCK_TAGS) is not None

    @staticmethod
    def _failure(reason: ParseFailureReason, error_message: str) -> ParseResult:
        logger.warning(
            "parser.parse_failed",
            extra={"failure_reason": reason, "error_message": error_message},
        )
        return ParseResult(document=None, failure_reason=reason, error_message=error_message)


def normalize_inline_text(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def normalize_document_text(text: str) -> str:
    lines = [normalize_inline_text(line) for line in text.splitlines()]
    meaningful_lines = [line for line in lines if line]
    deduped_lines: list[str] = []
    previous_line: str | None = None

    for line in meaningful_lines:
        if line != previous_line:
            deduped_lines.append(line)
        previous_line = line

    return BLANK_LINES_RE.sub("\n\n", "\n".join(deduped_lines)).strip()
