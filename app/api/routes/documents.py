import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session
from app.api.query_params import normalize_query
from app.api.schemas.documents import DocumentList, DocumentRead
from app.search.documents import DocumentQuery, DocumentQueryService, DocumentSort, SortOrder

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=DocumentList)
def list_documents(
    session: Annotated[Session, Depends(get_db_session)],
    q: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    source_id: uuid.UUID | None = None,
    is_active: bool | None = None,
    sort: DocumentSort = DocumentSort.last_changed_at,
    order: SortOrder = SortOrder.desc,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentList:
    normalized_query = normalize_query(q)
    query = DocumentQuery(
        q=normalized_query,
        source_id=source_id,
        is_active=is_active,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    result = DocumentQueryService(session).list_documents(query)
    return DocumentList(items=result.items, total=result.total, limit=limit, offset=offset)


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(
    document_id: uuid.UUID,
    session: Annotated[Session, Depends(get_db_session)],
) -> DocumentRead:
    document = DocumentQueryService(session).get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentRead.model_validate(document)
