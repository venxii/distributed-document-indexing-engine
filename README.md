# IndexFlow

**Incremental Document Indexing Engine**

IndexFlow is a backend engineering project that keeps a searchable index synchronized with external documents that change over time.

The current document sources are software company career pages, but the project is **not** a job portal. The core engineering problem is an indexing pipeline:

```text
crawl -> parse -> canonicalize -> hash -> detect changes -> store -> query
```

The system is intentionally built as one modular FastAPI backend. It is designed with clear module boundaries so the crawler, indexing pipeline, and query API can later be separated into independently deployable services if workload demands it.

## Why This Project Exists

Most backend projects demonstrate CRUD. IndexFlow focuses on a more systems-oriented problem:

> How do we efficiently ingest changing external documents, avoid unnecessary reprocessing, preserve indexed state correctly, and expose the result through a query API?

The engineering emphasis is on:

- asynchronous I/O
- HTML parsing and canonicalization
- content hashing
- idempotent incremental indexing
- PostgreSQL transactions and constraints
- REST API design
- query measurement before optimization
- avoiding premature infrastructure

## Architecture

```mermaid
flowchart TD
    source["External Source URL"] --> crawler["Crawler<br/>httpx, timeout, retry, robots.txt, rate limit"]
    crawler --> snapshot["Fetched HTML Snapshot"]
    snapshot --> parser["Parser<br/>BeautifulSoup"]
    parser --> parsed["ParsedDocument<br/>canonical_url, title, headings, normalized_text"]
    parsed --> hash["Canonical Representation<br/>SHA-256 Content Hash"]
    hash --> indexer["Incremental Indexer<br/>created / updated / unchanged"]
    indexer --> postgres[("PostgreSQL<br/>sources, crawl_runs, documents, document_versions")]
    postgres --> api["FastAPI REST API"]
    api --> client["Client Query"]
```

## Incremental Indexing Model

The heart of the project is hash-based change detection.

```mermaid
flowchart TD
    parsed["ParsedDocument"] --> canonical["Canonical JSON Representation"]
    canonical --> sha["SHA-256 content_hash"]
    sha --> lookup["Find current document by<br/>(source_id, canonical_url)"]
    lookup --> exists{"Document exists?"}
    exists -- "no" --> create["Create document<br/>Create version 1<br/>Return CREATED"]
    exists -- "yes" --> compare{"Hash matches current hash?"}
    compare -- "yes" --> unchanged["Update last_seen_at<br/>No new version<br/>Return UNCHANGED"]
    compare -- "no" --> update["Update current document<br/>Insert new version<br/>Return UPDATED"]
```

Core invariants:

- `(source_id, canonical_url)` identifies one current document.
- `content_hash` represents canonical parsed content, not crawl metadata.
- Reprocessing identical content is idempotent.
- Changed content creates exactly one new version.
- Document updates and version inserts are atomic.
- PostgreSQL constraints protect document identity under concurrency.

## What Was Built

### Crawler

The crawler fetches immutable snapshots of external pages.

Implemented:

- async crawling with `httpx`
- timeouts
- retry policies
- exponential backoff
- robots.txt awareness
- per-host rate limiting
- redirect handling
- failure classification

The crawler does **not** parse HTML, hash content, or write indexed documents.

### Parser

The parser converts heterogeneous HTML into a stable internal document representation.

```text
HTML -> ParsedDocument
```

The parser extracts:

- canonical URL
- title
- headings
- normalized text

It rejects unsupported, non-HTML, empty, and binary-like content. It intentionally does not extract structured job records, perform fuzzy matching, hash content, or write to the database.

### Incremental Indexer

The indexer compares the new parsed document hash with the current stored hash.

Possible outcomes:

```text
CREATED
UPDATED
UNCHANGED
FAILED
```

It stores:

- current indexed document state in `documents`
- distinct successfully indexed content states in `document_versions`

The indexer is designed to be idempotent under repeated processing.

### PostgreSQL Validation

The indexing design was validated against PostgreSQL, not only SQLite.

Validated:

- unique constraints
- concurrent first ingestion
- idempotent reprocessing
- changed-content updates
- transaction rollback behavior
- schema and index existence

### REST Query API

Read-only endpoints expose indexed state:

```http
GET /health
GET /sources
GET /sources/{source_id}
GET /sources/{source_id}/documents
GET /documents
GET /documents/{document_id}
```

Document search is intentionally a filter on documents:

```http
GET /documents?q=backend
```

A separate `/search` endpoint was deferred because search does not yet have independent semantics like ranking, relevance scoring, or custom query syntax.

API features:

- request validation
- response schemas
- pagination
- filtering
- sorting
- `404` behavior
- database-side querying

## Database Schema

```mermaid
erDiagram
    sources ||--o{ crawl_runs : has
    sources ||--o{ documents : owns
    documents ||--o{ document_versions : records

    sources {
        uuid id PK
        string name
        text careers_url
        boolean is_active
        int crawl_interval_seconds
        datetime last_crawled_at
        datetime created_at
        datetime updated_at
    }

    crawl_runs {
        uuid id PK
        uuid source_id FK
        datetime started_at
        datetime finished_at
        enum status
        int http_status
        text error_message
        int fetched_bytes
        int duration_ms
    }

    documents {
        uuid id PK
        uuid source_id FK
        text canonical_url
        string title
        text normalized_text
        string content_hash
        datetime first_seen_at
        datetime last_seen_at
        datetime last_changed_at
        boolean is_active
    }

    document_versions {
        uuid id PK
        uuid document_id FK
        string content_hash
        string title
        text normalized_text
        datetime created_at
    }
```

Important constraints and indexes:

- `UNIQUE(source_id, canonical_url)`
- `UNIQUE(document_id, content_hash)`
- index on `documents.source_id`
- index on `documents.content_hash`
- index on `document_versions.document_id`

## Query Performance Findings

Phase 5C measured direct database query service latency against FastAPI endpoint latency.

At 10,000 benchmark documents:

| Query | API p50 |
| --- | ---: |
| `/documents?limit=25&offset=0` | 4.77 ms |
| `/documents?limit=25&offset=1000` | 6.09 ms |
| `/documents?source_id=...` | 2.84 ms |
| `/documents?q=engineer` | 10.68 ms |
| `/documents?q=rareterm` | 34.31 ms |

Conclusion:

- FastAPI overhead is modest.
- PostgreSQL listing and source filtering are fine at this scale.
- Offset pagination is acceptable for now.
- The measured weak path is simple `ILIKE` text search.
- Redis is not justified because the measured bottleneck is not repeated cached reads.
- Elasticsearch is not justified because PostgreSQL has not yet been proven insufficient.

The most defensible next technical improvement would be a narrow PostgreSQL search-indexing experiment using full-text search or trigram indexes, measured against the current baseline.

## Technologies

Core stack:

- Python
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Docker Compose
- asyncio
- httpx
- BeautifulSoup
- pytest
- ruff
- mypy

Intentionally not used yet:

- Redis
- Elasticsearch/OpenSearch
- Kafka/RabbitMQ/SQS
- Celery
- Kubernetes
- Playwright
- S3

Those are not rejected forever. They are deferred until they solve an observed problem.

## Local Setup

Create and activate a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -e ".[dev]"
```

Start PostgreSQL:

```bash
docker compose up -d postgres
```

Apply migrations:

```bash
DATABASE_URL=postgresql+psycopg://indexflow:indexflow@127.0.0.1:5432/indexflow \
  alembic upgrade head
```

Run the API:

```bash
DATABASE_URL=postgresql+psycopg://indexflow:indexflow@127.0.0.1:5432/indexflow \
  uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000/docs
```

## Useful Commands

Run the full local test suite:

```bash
pytest
```

Run PostgreSQL integration tests:

```bash
POSTGRES_TEST_DATABASE_URL=postgresql+psycopg://indexflow:indexflow@127.0.0.1:5432/indexflow \
  pytest tests/test_indexing_postgres.py
```

Run static checks:

```bash
ruff check .
mypy .
```

Seed benchmark data:

```bash
python scripts/seed_benchmark_data.py \
  --database-url postgresql+psycopg://indexflow:indexflow@127.0.0.1:5432/indexflow \
  --reset \
  --documents 10000 \
  --sources 10
```

Run query benchmarks:

```bash
python scripts/benchmark_queries.py \
  --database-url postgresql+psycopg://indexflow:indexflow@127.0.0.1:5432/indexflow \
  --api-base-url http://127.0.0.1:8000
```

## Testing

The project includes tests for:

- crawler success and failure behavior
- retries and backoff
- robots.txt handling
- rate limiting
- parser determinism and boundary cases
- content hashing
- idempotent indexing
- changed-content updates
- transaction rollback
- concurrent ingestion
- PostgreSQL constraints and indexes
- REST API pagination, filtering, sorting, search, and not-found behavior

Recent validation:

```text
ruff: passed
mypy: passed
pytest: 32 passed, 5 skipped
PostgreSQL tests: 5 passed
```

The skipped tests are PostgreSQL integration tests unless `POSTGRES_TEST_DATABASE_URL` is set.

## Design Decisions

The most important design decisions are documented in [docs/decisions.md](docs/decisions.md).

Examples:

- Why incremental, not distributed?
- Why PostgreSQL first?
- Why no Redis initially?
- Why no Elasticsearch initially?
- Why hash-based change detection?
- Why document versions but not index events?
- Why search as `GET /documents?q=...`?
- Why benchmark before adding search infrastructure?

## Scaling Path

IndexFlow is not currently a distributed system. The intended evolution is:

```text
single modular backend
        ↓
better batching and indexes
        ↓
PostgreSQL search indexing if justified
        ↓
separate crawler/index workers if API responsiveness suffers
        ↓
multiple workers
        ↓
shared coordination only if necessary
        ↓
independently deployable services
```

This is deliberate. The project demonstrates incremental engineering judgment instead of adding infrastructure for resume optics.

## Current Conclusion

IndexFlow now has the core backend story:

```text
external documents
      ↓
reliable snapshot fetching
      ↓
stable parsing
      ↓
hash-based incremental indexing
      ↓
transactional PostgreSQL storage
      ↓
REST query API
      ↓
measured query behavior
```

The system is strong enough to present as a resume project today.

If development continues, the next highest-value technical phase is not Redis or Elasticsearch. It is a focused PostgreSQL search-indexing experiment measured against the Phase 5C baseline.
