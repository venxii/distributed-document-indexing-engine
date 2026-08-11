from dataclasses import dataclass
from enum import Enum


class ParseFailureReason(str, Enum):
    empty_content = "empty_content"
    non_html_content = "non_html_content"
    no_meaningful_text = "no_meaningful_text"


@dataclass(frozen=True)
class ParserConfig:
    min_text_length: int = 40

    def __post_init__(self) -> None:
        if self.min_text_length < 1:
            raise ValueError("min_text_length must be at least 1")


@dataclass(frozen=True)
class ParsedDocument:
    source_url: str
    final_url: str
    canonical_url: str
    title: str | None
    normalized_text: str
    headings: tuple[str, ...]


@dataclass(frozen=True)
class ParseResult:
    document: ParsedDocument | None
    failure_reason: ParseFailureReason | None
    error_message: str | None

    @property
    def succeeded(self) -> bool:
        return self.document is not None and self.failure_reason is None

