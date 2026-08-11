import sqlite3
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import Document, DocumentVersion, Source
from app.indexing.hashing import content_hash
from app.indexing.service import DocumentIndexer
from app.indexing.types import IndexingStatus
from app.parser.types import ParsedDocument


class ManualClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        value = self.current
        self.current = self.current + timedelta(seconds=1)
        return value


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    try:
        with SessionLocal() as db_session:
            yield db_session
    finally:
        engine.dispose()


def make_source(session: Session, name: str = "Example") -> Source:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    source = Source(
        name=name,
        careers_url=f"https://{name.lower()}.example.com/careers",
        is_active=True,
        crawl_interval_seconds=86400,
        created_at=now,
        updated_at=now,
    )
    session.add(source)
    session.commit()
    return source


def make_document(
    canonical_url: str = "https://example.com/careers",
    title: str | None = "Example Careers",
    text: str = "Backend Engineer\nBuild reliable indexing systems.",
    headings: tuple[str, ...] = ("Example Careers",),
    source_url: str = "https://example.com/jobs",
    final_url: str = "https://example.com/careers",
) -> ParsedDocument:
    return ParsedDocument(
        source_url=source_url,
        final_url=final_url,
        canonical_url=canonical_url,
        title=title,
        normalized_text=text,
        headings=headings,
    )


def count_rows(session: Session, model: type[Document] | type[DocumentVersion]) -> int:
    count = session.scalar(select(func.count()).select_from(model)) or 0
    session.rollback()
    return count


def test_hash_excludes_parser_url_metadata() -> None:
    document = make_document()
    same_content_different_metadata = make_document(
        canonical_url="https://other.example.com/new-canonical",
        source_url="https://other.example.com/jobs",
        final_url="https://other.example.com/redirected",
    )

    assert content_hash(document) == content_hash(same_content_different_metadata)


def test_hash_changes_when_title_or_content_changes() -> None:
    document = make_document()
    title_changed = make_document(title="New Careers Title")
    content_changed = make_document(text="Principal Backend Engineer\nBuild indexing systems.")

    assert content_hash(document) != content_hash(title_changed)
    assert content_hash(document) != content_hash(content_changed)


def test_first_document_creates_current_row_and_version_one(session: Session) -> None:
    source = make_source(session)
    parsed_document = make_document()

    result = DocumentIndexer(session, clock=ManualClock()).index(source.id, parsed_document)

    assert result.status == IndexingStatus.created
    assert result.version_created is True
    assert count_rows(session, Document) == 1
    assert count_rows(session, DocumentVersion) == 1

    document = session.scalar(select(Document))
    version = session.scalar(select(DocumentVersion))

    assert document is not None
    assert version is not None
    assert document.content_hash == result.content_hash
    assert version.content_hash == result.content_hash
    assert version.document_id == document.id


def test_same_document_again_is_unchanged_and_creates_no_version(session: Session) -> None:
    source = make_source(session)
    parsed_document = make_document()
    clock = ManualClock()
    indexer = DocumentIndexer(session, clock=clock)

    created = indexer.index(source.id, parsed_document)
    unchanged = indexer.index(source.id, parsed_document)

    assert created.status == IndexingStatus.created
    assert unchanged.status == IndexingStatus.unchanged
    assert unchanged.version_created is False
    assert count_rows(session, Document) == 1
    assert count_rows(session, DocumentVersion) == 1

    document = session.scalar(select(Document))
    assert document is not None
    assert document.last_seen_at > document.last_changed_at


def test_changed_content_updates_current_row_and_adds_one_version(session: Session) -> None:
    source = make_source(session)
    clock = ManualClock()
    indexer = DocumentIndexer(session, clock=clock)

    created = indexer.index(source.id, make_document())
    updated = indexer.index(
        source.id,
        make_document(text="Staff Backend Engineer\nOwn incremental indexing reliability."),
    )

    assert created.status == IndexingStatus.created
    assert updated.status == IndexingStatus.updated
    assert updated.version_created is True
    assert count_rows(session, Document) == 1
    assert count_rows(session, DocumentVersion) == 2

    document = session.scalar(select(Document))
    assert document is not None
    assert document.content_hash == updated.content_hash
    assert document.last_changed_at > document.first_seen_at


def test_same_changed_content_again_is_unchanged(session: Session) -> None:
    source = make_source(session)
    clock = ManualClock()
    indexer = DocumentIndexer(session, clock=clock)
    changed_document = make_document(text="Staff Backend Engineer\nOwn indexing reliability.")

    indexer.index(source.id, make_document())
    updated = indexer.index(source.id, changed_document)
    unchanged = indexer.index(source.id, changed_document)

    assert updated.status == IndexingStatus.updated
    assert unchanged.status == IndexingStatus.unchanged
    assert count_rows(session, Document) == 1
    assert count_rows(session, DocumentVersion) == 2


def test_idempotency_repeated_processing_converges(session: Session) -> None:
    source = make_source(session)
    source_id = source.id
    indexer = DocumentIndexer(session, clock=ManualClock())
    first_state = make_document()
    second_state = make_document(text="Changed meaningful page content for indexing.")

    for _ in range(10):
        indexer.index(source_id, first_state)

    assert count_rows(session, Document) == 1
    assert count_rows(session, DocumentVersion) == 1

    for _ in range(10):
        indexer.index(source_id, second_state)

    assert count_rows(session, Document) == 1
    assert count_rows(session, DocumentVersion) == 2


def test_different_urls_create_separate_documents(session: Session) -> None:
    source = make_source(session)
    indexer = DocumentIndexer(session, clock=ManualClock())

    indexer.index(source.id, make_document(canonical_url="https://example.com/careers"))
    indexer.index(source.id, make_document(canonical_url="https://example.com/university"))

    assert count_rows(session, Document) == 2
    assert count_rows(session, DocumentVersion) == 2


def test_same_url_and_same_source_reuses_document(session: Session) -> None:
    source = make_source(session)
    indexer = DocumentIndexer(session, clock=ManualClock())

    first = indexer.index(source.id, make_document())
    second = indexer.index(source.id, make_document())

    assert first.document_id == second.document_id
    assert count_rows(session, Document) == 1


def test_same_url_under_different_sources_creates_separate_documents(session: Session) -> None:
    first_source = make_source(session, "First")
    second_source = make_source(session, "Second")
    indexer = DocumentIndexer(session, clock=ManualClock())
    parsed_document = make_document(canonical_url="https://shared.example.com/careers")

    indexer.index(first_source.id, parsed_document)
    indexer.index(second_source.id, parsed_document)

    assert count_rows(session, Document) == 2
    assert count_rows(session, DocumentVersion) == 2


def test_failed_transaction_leaves_no_partial_state(session: Session) -> None:
    source = make_source(session)

    class FailingIndexer(DocumentIndexer):
        def _add_version(
            self,
            document: Document,
            parsed_document: ParsedDocument,
            new_hash: str,
            now: datetime,
        ) -> None:
            raise SQLAlchemyError("simulated version insert failure")

    result = FailingIndexer(session, clock=ManualClock()).index(source.id, make_document())

    assert result.status == IndexingStatus.failed
    assert count_rows(session, Document) == 0
    assert count_rows(session, DocumentVersion) == 0


def test_two_concurrent_first_ingestions_create_one_document(tmp_path: Path) -> None:
    database_path = tmp_path / "indexing.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection: sqlite3.Connection, _: object) -> None:
        dbapi_connection.execute("PRAGMA journal_mode=WAL")

    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

    with SessionLocal() as setup_session:
        source = make_source(setup_session)
        source_id = source.id

    parsed_document = make_document()

    def run_indexing() -> IndexingStatus:
        with SessionLocal() as worker_session:
            result = DocumentIndexer(worker_session, clock=ManualClock()).index(
                source_id,
                parsed_document,
            )
            return result.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(lambda _: run_indexing(), range(2)))

    with SessionLocal() as verify_session:
        assert count_rows(verify_session, Document) == 1
        assert count_rows(verify_session, DocumentVersion) == 1

    engine.dispose()

    assert IndexingStatus.created in statuses
    assert set(statuses).issubset({IndexingStatus.created, IndexingStatus.unchanged})
