import enum
import uuid
from dataclasses import dataclass

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Document


class DocumentSort(str, enum.Enum):
    first_seen_at = "first_seen_at"
    last_seen_at = "last_seen_at"
    last_changed_at = "last_changed_at"
    title_text = "title"


class SortOrder(str, enum.Enum):
    asc = "asc"
    desc = "desc"


@dataclass(frozen=True)
class DocumentQuery:
    q: str | None = None
    source_id: uuid.UUID | None = None
    is_active: bool | None = None
    sort: DocumentSort = DocumentSort.last_changed_at
    order: SortOrder = SortOrder.desc
    limit: int = 25
    offset: int = 0


@dataclass(frozen=True)
class DocumentQueryResult:
    items: list[Document]
    total: int


class DocumentQueryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_documents(self, query: DocumentQuery) -> DocumentQueryResult:
        base_statement = self._apply_filters(select(Document), query)
        total = self.session.scalar(
            select(func.count()).select_from(base_statement.subquery()),
        )
        sorted_statement = self._apply_sort(base_statement, query)
        paginated_statement = sorted_statement.limit(query.limit).offset(query.offset)
        items = list(self.session.scalars(paginated_statement).all())
        return DocumentQueryResult(items=items, total=total or 0)

    def get_document(self, document_id: uuid.UUID) -> Document | None:
        return self.session.get(Document, document_id)

    def _apply_filters(self, statement: Select[tuple[Document]], query: DocumentQuery) -> Select[tuple[Document]]:
        if query.source_id is not None:
            statement = statement.where(Document.source_id == query.source_id)
        if query.is_active is not None:
            statement = statement.where(Document.is_active == query.is_active)
        if query.q is not None:
            pattern = f"%{escape_like(query.q)}%"
            statement = statement.where(
                or_(
                    Document.title.ilike(pattern, escape="\\"),
                    Document.normalized_text.ilike(pattern, escape="\\"),
                ),
            )
        return statement

    def _apply_sort(self, statement: Select[tuple[Document]], query: DocumentQuery) -> Select[tuple[Document]]:
        sort_column = getattr(Document, query.sort.value)
        if query.order == SortOrder.desc:
            sort_column = sort_column.desc()
        else:
            sort_column = sort_column.asc()
        return statement.order_by(sort_column, Document.id.asc())


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
