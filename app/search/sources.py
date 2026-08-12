import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Source


@dataclass(frozen=True)
class SourceQuery:
    is_active: bool | None = None
    limit: int = 25
    offset: int = 0


@dataclass(frozen=True)
class SourceQueryResult:
    items: list[Source]
    total: int


class SourceQueryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_sources(self, query: SourceQuery) -> SourceQueryResult:
        statement = select(Source)
        if query.is_active is not None:
            statement = statement.where(Source.is_active == query.is_active)

        total = self.session.scalar(select(func.count()).select_from(statement.subquery()))
        items = list(
            self.session.scalars(
                statement.order_by(Source.name.asc(), Source.id.asc())
                .limit(query.limit)
                .offset(query.offset),
            ).all(),
        )
        return SourceQueryResult(items=items, total=total or 0)

    def get_source(self, source_id: uuid.UUID) -> Source | None:
        return self.session.get(Source, source_id)
