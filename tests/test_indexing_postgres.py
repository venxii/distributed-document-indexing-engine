import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, func, inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from app.db.models import Document, DocumentVersion, Source
from app.indexing.service import DocumentIndexer
from app.indexing.types import IndexingStatus
from app.parser.types import ParsedDocument

POSTGRES_TEST_DATABASE_URL = os.getenv("POSTGRES_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not POSTGRES_TEST_DATABASE_URL,
    reason="set POSTGRES_TEST_DATABASE_URL to run PostgreSQL integration tests",
)


class ManualClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        value = self.current
        self.current = self.current + timedelta(seconds=1)
        return value


@pytest.fixture(scope="module")
def postgres_engine() -> Iterator[Engine]:
    if POSTGRES_TEST_DATABASE_URL is None:
        raise RuntimeError("POSTGRES_TEST_DATABASE_URL is required")

    engine = create_engine(POSTGRES_TEST_DATABASE_URL)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def migrated_schema(postgres_engine: Engine) -> Iterator[None]:
    reset_public_schema(postgres_engine)
    alembic_config = Config("alembic.ini")
    alembic_config.set_main_option("sqlalchemy.url", str(postgres_engine.url))
    command.upgrade(alembic_config, "head")
    yield
    reset_public_schema(postgres_engine)


@pytest.fixture
def session_factory(postgres_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=postgres_engine, expire_on_commit=False)


def reset_public_schema(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))


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
) -> ParsedDocument:
    return ParsedDocument(
        source_url="https://example.com/jobs",
        final_url="https://example.com/careers",
        canonical_url=canonical_url,
        title=title,
        normalized_text=text,
        headings=("Example Careers",),
    )


def count_rows(session: Session, model: type[Document] | type[DocumentVersion]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_postgres_schema_contains_required_constraints_and_indexes(
    postgres_engine: Engine,
) -> None:
    inspector = inspect(postgres_engine)

    assert set(inspector.get_table_names()) >= {
        "sources",
        "crawl_runs",
        "documents",
        "document_versions",
    }

    document_constraints = {
        constraint["name"] for constraint in inspector.get_unique_constraints("documents")
    }
    version_constraints = {
        constraint["name"] for constraint in inspector.get_unique_constraints("document_versions")
    }
    document_indexes = {index["name"] for index in inspector.get_indexes("documents")}
    version_indexes = {index["name"] for index in inspector.get_indexes("document_versions")}

    assert "uq_documents_source_canonical_url" in document_constraints
    assert "uq_document_versions_document_hash" in version_constraints
    assert "ix_documents_source_id" in document_indexes
    assert "ix_documents_content_hash" in document_indexes
    assert "ix_document_versions_document_id" in version_indexes


def test_postgres_idempotent_reprocessing(session_factory: sessionmaker[Session]) -> None:
    with session_factory() as session:
        source = make_source(session)
        source_id = source.id

    first_state = make_document()
    second_state = make_document(text="Changed meaningful page content for indexing.")

    for _ in range(10):
        with session_factory() as session:
            DocumentIndexer(session, clock=ManualClock()).index(source_id, first_state)

    with session_factory() as session:
        assert count_rows(session, Document) == 1
        assert count_rows(session, DocumentVersion) == 1

    for _ in range(10):
        with session_factory() as session:
            DocumentIndexer(session, clock=ManualClock()).index(source_id, second_state)

    with session_factory() as session:
        assert count_rows(session, Document) == 1
        assert count_rows(session, DocumentVersion) == 2


def test_postgres_changed_content_creates_exactly_one_new_version(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        source = make_source(session)
        source_id = source.id
        indexer = DocumentIndexer(session, clock=ManualClock())

        created = indexer.index(source_id, make_document())
        updated = indexer.index(
            source_id,
            make_document(text="Staff Backend Engineer\nOwn indexing reliability."),
        )

        assert created.status == IndexingStatus.created
        assert updated.status == IndexingStatus.updated
        assert count_rows(session, Document) == 1
        assert count_rows(session, DocumentVersion) == 2


def test_postgres_failed_transaction_leaves_no_partial_state(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        source = make_source(session)

        class FailingIndexer(DocumentIndexer):
            def _add_version(
                self,
                document: Document,
                parsed_document: ParsedDocument,
                new_hash: str,
                now: datetime,
            ) -> None:
                raise SQLAlchemyError("simulated failure after document insert")

        result = FailingIndexer(session, clock=ManualClock()).index(source.id, make_document())

        assert result.status == IndexingStatus.failed
        assert count_rows(session, Document) == 0
        assert count_rows(session, DocumentVersion) == 0


def test_postgres_concurrent_first_ingestion_converges_to_one_document(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        source = make_source(session)
        source_id = source.id

    parsed_document = make_document()

    def run_indexing() -> IndexingStatus:
        with session_factory() as worker_session:
            result = DocumentIndexer(worker_session, clock=ManualClock()).index(
                source_id,
                parsed_document,
            )
            return result.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(lambda _: run_indexing(), range(2)))

    with session_factory() as session:
        assert count_rows(session, Document) == 1
        assert count_rows(session, DocumentVersion) == 1

    assert IndexingStatus.created in statuses
    assert set(statuses).issubset({IndexingStatus.created, IndexingStatus.unchanged})
