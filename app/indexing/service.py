import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentVersion
from app.indexing.hashing import content_hash
from app.indexing.types import IndexingResult, IndexingStatus
from app.parser.types import ParsedDocument

logger = logging.getLogger(__name__)
Clock = Callable[[], datetime]


class DocumentIndexer:
    """Maintains the current indexed document state and distinct content versions."""

    def __init__(self, session: Session, clock: Clock | None = None) -> None:
        self._session = session
        self._clock = clock or (lambda: datetime.now(UTC))

    def index(self, source_id: uuid.UUID, parsed_document: ParsedDocument) -> IndexingResult:
        new_hash = content_hash(parsed_document)

        for attempt in range(2):
            try:
                return self._index_once(source_id, parsed_document, new_hash)
            except IntegrityError as exc:
                self._session.rollback()
                if attempt == 0:
                    logger.warning(
                        "indexing.integrity_retry",
                        extra={
                            "source_id": str(source_id),
                            "canonical_url": parsed_document.canonical_url,
                        },
                    )
                    continue
                return self._failed_result(new_hash, exc)
            except SQLAlchemyError as exc:
                self._session.rollback()
                return self._failed_result(new_hash, exc)

        return IndexingResult(
            status=IndexingStatus.failed,
            document_id=None,
            content_hash=new_hash,
            version_created=False,
            error_message="indexing retry loop exited unexpectedly",
        )

    def _index_once(
        self,
        source_id: uuid.UUID,
        parsed_document: ParsedDocument,
        new_hash: str,
    ) -> IndexingResult:
        now = self._clock()
        with self._session.begin():
            document = self._find_document_for_update(source_id, parsed_document.canonical_url)

            if document is None:
                document = Document(
                    source_id=source_id,
                    canonical_url=parsed_document.canonical_url,
                    title=parsed_document.title,
                    normalized_text=parsed_document.normalized_text,
                    content_hash=new_hash,
                    first_seen_at=now,
                    last_seen_at=now,
                    last_changed_at=now,
                    is_active=True,
                )
                self._session.add(document)
                self._session.flush()
                self._add_version(document, parsed_document, new_hash, now)
                logger.info(
                    "indexing.document_created",
                    extra={"document_id": str(document.id), "content_hash": new_hash},
                )
                return IndexingResult(
                    status=IndexingStatus.created,
                    document_id=document.id,
                    content_hash=new_hash,
                    version_created=True,
                )

            if document.content_hash == new_hash:
                document.last_seen_at = now
                logger.info(
                    "indexing.document_unchanged",
                    extra={"document_id": str(document.id), "content_hash": new_hash},
                )
                return IndexingResult(
                    status=IndexingStatus.unchanged,
                    document_id=document.id,
                    content_hash=new_hash,
                    version_created=False,
                )

            document.title = parsed_document.title
            document.normalized_text = parsed_document.normalized_text
            document.content_hash = new_hash
            document.last_seen_at = now
            document.last_changed_at = now
            document.is_active = True
            self._add_version(document, parsed_document, new_hash, now)
            logger.info(
                "indexing.document_updated",
                extra={"document_id": str(document.id), "content_hash": new_hash},
            )
            return IndexingResult(
                status=IndexingStatus.updated,
                document_id=document.id,
                content_hash=new_hash,
                version_created=True,
            )

    def _find_document_for_update(self, source_id: uuid.UUID, canonical_url: str) -> Document | None:
        statement = (
            select(Document)
            .where(Document.source_id == source_id, Document.canonical_url == canonical_url)
            .with_for_update()
        )
        return self._session.scalar(statement)

    def _add_version(
        self,
        document: Document,
        parsed_document: ParsedDocument,
        new_hash: str,
        now: datetime,
    ) -> None:
        self._session.add(
            DocumentVersion(
                document_id=document.id,
                content_hash=new_hash,
                title=parsed_document.title,
                normalized_text=parsed_document.normalized_text,
                created_at=now,
            )
        )

    @staticmethod
    def _failed_result(new_hash: str, exc: SQLAlchemyError) -> IndexingResult:
        logger.exception("indexing.failed")
        return IndexingResult(
            status=IndexingStatus.failed,
            document_id=None,
            content_hash=new_hash,
            version_created=False,
            error_message=str(exc),
        )
