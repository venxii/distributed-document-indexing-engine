import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    canonical_url: str
    title: str | None
    normalized_text: str
    content_hash: str
    first_seen_at: datetime
    last_seen_at: datetime
    last_changed_at: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)


class DocumentList(BaseModel):
    items: list[DocumentRead]
    total: int
    limit: int
    offset: int
