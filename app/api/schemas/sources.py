import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SourceRead(BaseModel):
    id: uuid.UUID
    name: str
    careers_url: str
    is_active: bool
    crawl_interval_seconds: int
    last_crawled_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SourceList(BaseModel):
    items: list[SourceRead]
    total: int
    limit: int
    offset: int
