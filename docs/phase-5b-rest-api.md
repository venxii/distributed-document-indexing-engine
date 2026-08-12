# Phase 5B REST Query API Review

Phase 5B turns the indexed document store into a queryable backend service. It does not add new ingestion behavior.

## Problem Being Solved

Phase 4 can persist current documents and historical versions, but clients still cannot query the indexed state through HTTP.

The problem is:

> Expose current indexed documents and sources through a small, predictable REST API without adding a separate search system before we have evidence that one is needed.

## Possible Approaches

- Expose simple REST read endpoints backed by PostgreSQL queries.
- Add a separate `/search` endpoint.
- Add Elasticsearch/OpenSearch.
- Fetch rows into Python and filter in application code.
- Add a GraphQL API.

## Chosen Approach

Use FastAPI read endpoints:

```text
GET /health
GET /sources
GET /sources/{source_id}
GET /sources/{source_id}/documents
GET /documents
GET /documents/{document_id}
```

Search is currently a query dimension on documents:

```text
GET /documents?q=backend&source_id=...&sort=last_changed_at&order=desc&limit=25&offset=0
```

The API uses a layered structure:

```text
HTTP route
    ↓
Pydantic schema / query parameter validation
    ↓
query service
    ↓
SQLAlchemy
    ↓
PostgreSQL
```

## Why Alternatives Were Rejected

Separate `/search` endpoint:
Rejected for now because search is only case-insensitive filtering over current documents. A dedicated endpoint makes more sense once search has separate semantics such as ranking, relevance, tokenization, or query syntax.

Elasticsearch/OpenSearch:
Rejected because the system does not yet have a demonstrated corpus size, relevance, or query latency problem that PostgreSQL cannot handle.

Python-side filtering:
Rejected because it requires transferring unnecessary rows from the database to the application before filtering. The database should reduce the result set.

GraphQL:
Rejected because the current query shapes are simple and REST is easier to implement, test, document, and defend.

Document version endpoints:
Rejected for Phase 5B because the primary API consumer needs the current indexed document. Versions are an internal indexing correctness/debugging concern until a real historical inspection use case appears.

## Tradeoffs

Offset pagination is simple and easy to explain, but large offsets can become expensive.

`ILIKE` search is simple and database-side, but it does not provide ranking, stemming, tokenization, or strong performance over large text corpora.

Synchronous SQLAlchemy keeps the API aligned with the existing indexer and migration code, but each request uses a blocking database call. FastAPI runs sync route handlers in a worker thread, which is acceptable for the current architecture.

The API is read-only, which keeps scope narrow but means source creation and ingestion orchestration remain outside the public API for now.

## Failure Cases

- Invalid UUIDs return FastAPI validation errors.
- Invalid pagination values return validation errors.
- Whitespace-only search queries are rejected.
- Missing documents return `404`.
- Missing sources return `404`.
- Database failures surface as server errors until we add a more formal error mapping layer.

## How This Scales

At current scale, PostgreSQL-side filtering and offset pagination are sufficient.

The scaling path is:

1. Add indexes based on observed query patterns.
2. Replace `ILIKE` with PostgreSQL full-text search or trigram indexes if query latency or relevance becomes a problem.
3. Replace offset pagination with keyset pagination when high offsets become expensive.
4. Add Redis only if repeated read queries become measurably expensive.
5. Add Elasticsearch/OpenSearch only if PostgreSQL no longer satisfies search requirements.

## Validation

Implemented tests verify:

- Document listing.
- Case-insensitive document search through `q`.
- Source filtering.
- Sorting.
- Pagination metadata.
- Single document lookup.
- `404` behavior.
- Source document listing.
- Invalid pagination validation.
- Blank search rejection.

Current validation:

```text
ruff: passed
mypy: passed
pytest: 32 passed, 5 skipped
```

The skipped tests are PostgreSQL integration tests that run when `POSTGRES_TEST_DATABASE_URL` is set.

## Weakest Assumption

The weakest part of the current design is using simple `ILIKE` search because it may become slow or low-quality as the number of indexed documents grows.

We should not fix this now. It should be intentionally deferred to Phase 5C, where we can measure query behavior and decide whether PostgreSQL full-text search or trigram indexing is justified.

## SDE Competency Check

This phase demonstrates:

- REST API design.
- Request validation.
- Response schemas.
- Pagination.
- Filtering and sorting.
- Database-side querying.
- Separation between HTTP routes and query construction.
- Clear rejection of unnecessary search infrastructure.

Before moving on, be able to answer:

- Why is search implemented as `GET /documents?q=...` instead of `/search`?
- Why should filtering happen in PostgreSQL instead of Python?
- What is the cost of offset pagination?
- When would keyset pagination be justified?
- What problem would PostgreSQL full-text search solve?
- Why are document versions not exposed yet?
