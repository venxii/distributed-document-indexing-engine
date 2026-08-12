import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db_session
from app.db.base import Base
from app.db.models import Document, Source
from app.main import create_app


def test_list_documents_supports_search_filter_sort_and_pagination() -> None:
    client, session_factory = make_test_client()
    with session_factory() as session:
        source = create_source(session, name="Example")
        other_source = create_source(session, name="Other")
        create_document(
            session,
            source_id=source.id,
            canonical_url="https://example.com/backend",
            title="Backend Engineer",
            normalized_text="Build indexing systems.",
            last_changed_at=datetime(2026, 1, 3, tzinfo=UTC),
        )
        create_document(
            session,
            source_id=source.id,
            canonical_url="https://example.com/frontend",
            title="Frontend Engineer",
            normalized_text="Build product interfaces.",
            last_changed_at=datetime(2026, 1, 2, tzinfo=UTC),
        )
        create_document(
            session,
            source_id=other_source.id,
            canonical_url="https://other.example.com/backend",
            title="Backend Platform Engineer",
            normalized_text="Work on crawler reliability.",
            last_changed_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

    response = client.get(
        f"/documents?q=backend&source_id={source.id}&sort=last_changed_at&order=desc&limit=1&offset=0",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 1
    assert payload["offset"] == 0
    assert [item["title"] for item in payload["items"]] == ["Backend Engineer"]


def test_get_document_returns_document_or_404() -> None:
    client, session_factory = make_test_client()
    with session_factory() as session:
        source = create_source(session)
        document = create_document(session, source_id=source.id)
        document_id = document.id

    found_response = client.get(f"/documents/{document_id}")
    missing_response = client.get(f"/documents/{uuid.uuid4()}")

    assert found_response.status_code == 200
    assert found_response.json()["id"] == str(document_id)
    assert missing_response.status_code == 404


def test_documents_reject_invalid_pagination_and_blank_query() -> None:
    client, _ = make_test_client()

    invalid_limit = client.get("/documents?limit=0")
    blank_query = client.get("/documents?q=%20%20%20")

    assert invalid_limit.status_code == 422
    assert blank_query.status_code == 422


def test_list_sources_and_source_documents() -> None:
    client, session_factory = make_test_client()
    with session_factory() as session:
        source = create_source(session, name="Example")
        inactive_source = create_source(session, name="Inactive", is_active=False)
        create_document(session, source_id=source.id, title="Backend Engineer")
        create_document(session, source_id=inactive_source.id, title="Frontend Engineer")
        source_id = source.id

    sources_response = client.get("/sources?is_active=true")
    source_documents_response = client.get(f"/sources/{source_id}/documents?q=backend")
    missing_source_response = client.get(f"/sources/{uuid.uuid4()}/documents")

    assert sources_response.status_code == 200
    assert sources_response.json()["total"] == 1
    assert sources_response.json()["items"][0]["name"] == "Example"
    assert source_documents_response.status_code == 200
    assert source_documents_response.json()["total"] == 1
    assert missing_source_response.status_code == 404


def make_test_client() -> tuple[TestClient, sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override_session
    return TestClient(app), session_factory


def create_source(
    session: Session,
    name: str = "Example",
    is_active: bool = True,
) -> Source:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    source = Source(
        name=name,
        careers_url=f"https://{name.lower()}.example.com/careers",
        is_active=is_active,
        crawl_interval_seconds=86400,
        created_at=now,
        updated_at=now,
    )
    session.add(source)
    session.commit()
    return source


def create_document(
    session: Session,
    source_id: uuid.UUID,
    canonical_url: str = "https://example.com/careers",
    title: str | None = "Example Careers",
    normalized_text: str = "Backend Engineer\nBuild reliable indexing systems.",
    last_changed_at: datetime | None = None,
) -> Document:
    first_seen_at = datetime(2026, 1, 1, tzinfo=UTC)
    document = Document(
        source_id=source_id,
        canonical_url=canonical_url,
        title=title,
        normalized_text=normalized_text,
        content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        first_seen_at=first_seen_at,
        last_seen_at=first_seen_at + timedelta(days=1),
        last_changed_at=last_changed_at or first_seen_at,
        is_active=True,
    )
    session.add(document)
    session.commit()
    return document
