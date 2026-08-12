# Phase 5A PostgreSQL Integration Validation

Phase 5A is not a feature expansion. It validates that the Phase 4 indexing design behaves correctly against PostgreSQL, the database it was designed for.

## Goal

Answer one question:

> Does the indexing design we already built behave correctly against PostgreSQL?

This phase should not change indexing semantics unless PostgreSQL validation exposes a real correctness issue.

## Scope

In scope:

- Docker Compose PostgreSQL service.
- Application database URL configuration for local PostgreSQL.
- Schema setup through Alembic migrations or an equivalent explicit schema creation path.
- PostgreSQL-backed indexing validation tests.
- Constraint and index verification.
- Concurrent ingestion validation.
- Transaction rollback validation.
- SQLite vs PostgreSQL behavior notes.

Out of scope:

- Redis
- Kafka
- SQS
- Celery
- worker separation
- multiple services
- AWS
- Kubernetes
- Elasticsearch/OpenSearch
- Playwright
- `index_events`
- REST API endpoints
- search behavior

## Validation Order

```text
PostgreSQL starts
        ↓
Schema/migrations apply
        ↓
Basic indexing tests
        ↓
Constraint tests
        ↓
Rollback test
        ↓
Concurrent ingestion test
        ↓
Compare against SQLite
        ↓
Document results
        ↓
STOP
```

## Schema Requirements

PostgreSQL must contain the current Phase 4 tables and constraints:

```text
sources
crawl_runs
documents
document_versions
```

Required constraints and indexes:

```text
UNIQUE(source_id, canonical_url)
```

```text
UNIQUE(document_id, content_hash)
```

```text
INDEX documents(source_id)
```

```text
INDEX documents(content_hash)
```

```text
INDEX document_versions(document_id)
```

The validation should query PostgreSQL system catalogs or SQLAlchemy inspection metadata to confirm these exist. We should not rely only on model definitions.

## Required Tests

### 1. Unique Current Document

Scenario:

```text
same source_id
same canonical_url
same parsed content
```

Expected result:

```text
documents = 1
document_versions = 1
```

Purpose:
Validate that PostgreSQL enforces the logical document identity invariant.

### 2. Concurrent First Ingestion

Scenario:

```text
Worker A ───────┐
                ├── same source_id + canonical_url + content_hash
Worker B ───────┘
```

Both workers should be allowed to race naturally against PostgreSQL. The test should not serialize them in application code.

Expected final state:

```text
documents = 1
document_versions = 1
```

Acceptable worker-level behavior:

- One worker returns `CREATED`.
- The other worker may encounter a uniqueness conflict, roll back, re-read the existing row, and return `UNCHANGED`.

Unacceptable behavior:

- Two document rows.
- Two version rows for the same `(document_id, content_hash)`.
- A failed transaction that leaves partial state.
- A uniqueness conflict escaping as an unhandled error when it can be resolved by re-reading.

Design implication:
If PostgreSQL exposes a race that SQLite did not, the fix should stay inside the indexer transaction/conflict handling path. Do not add Redis locks or queues.

### 3. Idempotent Reprocessing

Scenario:

```text
process same ParsedDocument 10 times
```

Expected result:

```text
documents = 1
document_versions = 1
```

Then:

```text
process changed ParsedDocument 10 times
```

Expected result:

```text
documents = 1
document_versions = 2
```

Purpose:
Validate that repeated processing converges and storage grows with distinct content states, not crawl count.

### 4. Changed Content

Scenario:

```text
same source_id
same canonical_url
different canonical content
```

Expected result:

```text
status = UPDATED
documents = 1
document_versions = 2
current document hash = new hash
```

Purpose:
Validate exact hash-based change detection against real PostgreSQL writes.

### 5. Rollback After Partial Work

Scenario:
Deliberately fail inside a transaction after one database operation has occurred.

Example:

```text
insert documents row
force failure before/while inserting document_versions row
```

Expected result:

```text
documents = 0
document_versions = 0
```

Purpose:
Validate atomicity. We are not testing rollback if the failure happens before any write; the failure must occur after at least one database operation.

### 6. Schema And Index Verification

Scenario:
Inspect PostgreSQL schema after migrations/schema setup.

Expected result:

- Required tables exist.
- Required unique constraints exist.
- Required indexes exist.
- Column types are appropriate for PostgreSQL.

Purpose:
Validate that the actual database matches the design, not merely the SQLAlchemy model.

## SQLite vs PostgreSQL Comparison

The Phase 4 SQLite tests remain useful for fast local service validation, but they do not prove PostgreSQL behavior.

The Phase 5A notes should explicitly compare:

- uniqueness conflict behavior
- transaction behavior
- row locking behavior
- concurrent writes
- type differences, especially UUID handling
- any SQLAlchemy behavior that differs by dialect

If the behaviors match for the tested invariants, document that. If not, document the difference and decide whether it requires an indexer change.

## Expected Implementation Shape

Phase 5A should likely add:

```text
docker-compose.yml
alembic.ini
alembic/
tests/test_indexing_postgres.py
docs/phase-5a-postgresql-validation.md
```

This is not permission to add unrelated infrastructure. Each file must directly support PostgreSQL validation.

## Local Validation Commands

Docker Compose workflow:

```bash
docker compose up -d postgres
```

```bash
DATABASE_URL=postgresql+psycopg://indexflow:indexflow@localhost:5432/indexflow \
  .venv/bin/alembic upgrade head
```

```bash
POSTGRES_TEST_DATABASE_URL=postgresql+psycopg://indexflow:indexflow@localhost:5432/indexflow \
  .venv/bin/python -m pytest tests/test_indexing_postgres.py
```

The regular test suite should still run without PostgreSQL. PostgreSQL integration tests should skip unless `POSTGRES_TEST_DATABASE_URL` is set.

If Docker is unavailable but PostgreSQL is installed locally, an isolated local cluster is also acceptable because Phase 5A is validating PostgreSQL behavior, not Docker itself. In this run, PostgreSQL 14.17 from Homebrew was used on port `55432`.

## Stop Condition

Phase 5A is complete when:

- PostgreSQL starts locally.
- Schema setup is reproducible.
- PostgreSQL indexing tests pass.
- Constraint/index existence is verified.
- SQLite vs PostgreSQL differences are documented.
- No new unapproved infrastructure has been introduced.

Then stop before Phase 5B REST API.

## Current Implementation Status

Added:

- `docker-compose.yml` for local PostgreSQL.
- Alembic configuration and initial schema migration.
- PostgreSQL-specific indexing validation tests in `tests/test_indexing_postgres.py`.
- `psycopg` driver dependency.

Current local validation result in this Codex environment:

- `pytest tests/test_indexing_postgres.py -vv`: 5 passed against PostgreSQL 14.17.
- `pytest --cov=app --cov-report=term-missing` with `POSTGRES_TEST_DATABASE_URL` set: 33 passed.
- `ruff`: all checks passed.
- `mypy`: no issues found in 33 source files.
- Docker is not installed in this environment, so validation used a local Homebrew PostgreSQL runtime instead of Docker Compose.

The skipped PostgreSQL tests are intentional unless `POSTGRES_TEST_DATABASE_URL` is set. When set, the PostgreSQL tests run as part of the full suite.

Phase 5A PostgreSQL runtime validation is complete for the tested invariants.

## SQLite vs PostgreSQL Findings

- Schema/index verification is meaningful only against PostgreSQL; the PostgreSQL test inspected actual database metadata.
- Idempotent reprocessing behaved the same under SQLite and PostgreSQL.
- Changed-content version creation behaved the same under SQLite and PostgreSQL.
- Rollback after a document insert and before version persistence left no partial state under PostgreSQL.
- Concurrent first ingestion converged to one document and one version under PostgreSQL.
- No Phase 4 indexer changes were required.
- Docker Compose itself remains untested here because Docker is not installed, but the database behavior Phase 5A was designed to validate has been exercised against real PostgreSQL.

## Weakest Assumption

The weakest remaining part is that Docker Compose startup has not been tested in this environment because Docker is unavailable.

This should not block Phase 5B, because the actual PostgreSQL runtime behavior has been validated with a local PostgreSQL server. Docker Compose should still be tested later before deployment or handoff.
