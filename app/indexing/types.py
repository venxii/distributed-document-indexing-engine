import uuid
from dataclasses import dataclass
from enum import Enum


class IndexingStatus(str, Enum):
    created = "created"
    updated = "updated"
    unchanged = "unchanged"
    failed = "failed"


@dataclass(frozen=True)
class IndexingResult:
    status: IndexingStatus
    document_id: uuid.UUID | None
    content_hash: str
    version_created: bool
    error_message: str | None = None

