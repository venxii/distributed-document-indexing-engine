import argparse
import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, delete
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.models import Document, DocumentVersion, Source

COMPANIES = (
    "Atlas",
    "Beacon",
    "Cloudline",
    "Delta",
    "Evergreen",
    "Forge",
    "Helios",
    "Ion",
    "Keystone",
    "Lattice",
)

ROLES = (
    "Backend Engineer",
    "Platform Engineer",
    "Infrastructure Engineer",
    "Frontend Engineer",
    "Data Engineer",
    "Security Engineer",
)

TERMS = (
    "backend",
    "crawler",
    "parser",
    "indexing",
    "postgresql",
    "reliability",
    "distributed",
    "observability",
    "latency",
    "rareterm",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed deterministic documents for query benchmarks.")
    parser.add_argument("--documents", type=int, default=10_000)
    parser.add_argument("--sources", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=1_000)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--database-url", default=settings.database_url)
    args = parser.parse_args()

    engine = create_engine(args.database_url, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        if args.reset:
            reset_data(session)
        sources = ensure_sources(session, args.sources)
        seed_documents(session, sources, args.documents, args.batch_size)

    engine.dispose()
    print(f"Seeded {args.documents} documents across {len(sources)} sources.")


def reset_data(session: Session) -> None:
    session.execute(delete(DocumentVersion))
    session.execute(delete(Document))
    session.execute(delete(Source))
    session.commit()


def ensure_sources(session: Session, count: int) -> list[Source]:
    existing = list(session.query(Source).order_by(Source.name.asc()).limit(count).all())
    if len(existing) >= count:
        return existing

    now = datetime(2026, 1, 1, tzinfo=UTC)
    sources = existing[:]
    for index in range(len(existing), count):
        name = COMPANIES[index % len(COMPANIES)]
        source = Source(
            name=f"{name} Careers {index + 1}",
            careers_url=f"https://{name.lower()}-{index + 1}.example.com/careers",
            is_active=True,
            crawl_interval_seconds=86400,
            created_at=now,
            updated_at=now,
        )
        session.add(source)
        sources.append(source)

    session.commit()
    return sources


def seed_documents(
    session: Session,
    sources: list[Source],
    document_count: int,
    batch_size: int,
) -> None:
    existing_count = session.query(Document).count()
    if existing_count >= document_count:
        return

    now = datetime(2026, 1, 1, tzinfo=UTC)
    pending: list[Document] = []
    for index in range(existing_count, document_count):
        source = sources[index % len(sources)]
        role = ROLES[index % len(ROLES)]
        primary_term = TERMS[index % len(TERMS)]
        secondary_term = TERMS[(index * 7) % len(TERMS)]
        content = (
            f"{role}\n"
            f"Build {primary_term} systems for document indexing pipelines. "
            f"Own {secondary_term} reliability, query latency, and operational correctness. "
            f"Benchmark cohort {index // max(len(sources), 1)}."
        )
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        seen_at = now + timedelta(seconds=index)
        pending.append(
            Document(
                source_id=source.id,
                canonical_url=f"{source.careers_url}/documents/{index}",
                title=f"{role} {index}",
                normalized_text=content,
                content_hash=content_hash,
                first_seen_at=seen_at,
                last_seen_at=seen_at,
                last_changed_at=seen_at,
                is_active=(index % 20 != 0),
            ),
        )

        if len(pending) >= batch_size:
            session.add_all(pending)
            session.commit()
            pending.clear()

    if pending:
        session.add_all(pending)
        session.commit()


if __name__ == "__main__":
    main()
