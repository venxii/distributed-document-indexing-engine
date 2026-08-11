import hashlib
import json

from app.parser.types import ParsedDocument


def canonical_content(document: ParsedDocument) -> str:
    payload = {
        "schema": "indexflow.parsed-document.v1",
        "title": document.title or "",
        "headings": list(document.headings),
        "normalized_text": document.normalized_text,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(document: ParsedDocument) -> str:
    return hashlib.sha256(canonical_content(document).encode("utf-8")).hexdigest()

