import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.api.query_params import normalize_query
from app.api.schemas.documents import DocumentList
from app.api.schemas.sources import SourceList, SourceRead
from app.search.documents import DocumentQuery, DocumentQueryService, DocumentSort, SortOrder
from app.search.sources import SourceQuery, SourceQueryService

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("", response_model=SourceList)
def list_sources(
    session: Annotated[Session, Depends(get_db_session)],
    is_active: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SourceList:
    result = SourceQueryService(session).list_sources(
        SourceQuery(is_active=is_active, limit=limit, offset=offset),
    )
    return SourceList(items=result.items, total=result.total, limit=limit, offset=offset)


@router.get("/{source_id}", response_model=SourceRead)
def get_source(
    source_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db_session)],
) -> SourceRead:
    source = SourceQueryService(session).get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return SourceRead.model_validate(source)


@router.get("/{source_id}/documents", response_model=DocumentList)
def list_source_documents(
    source_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db_session)],
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    is_active: bool | None = None,
    sort: DocumentSort = DocumentSort.last_changed_at,
    order: SortOrder = SortOrder.desc,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentList:
    if SourceQueryService(session).get_source(source_id) is None:
        raise HTTPException(status_code=404, detail="Source not found")

    result = DocumentQueryService(session).list_documents(
        DocumentQuery(
            q=normalize_query(q),
            source_id=source_id,
            is_active=is_active,
            sort=sort,
            order=order,
            limit=limit,
            offset=offset,
        ),
    )
    return DocumentList(items=result.items, total=result.total, limit=limit, offset=offset)
