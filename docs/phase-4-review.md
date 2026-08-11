# Phase 4 Review Checklist

Phase 4 is not considered complete until incremental indexing correctness is validated.

## Indexing Semantics

- [x] First document creates one current `documents` row.
- [x] First document creates version 1.
- [x] Same document content returns `UNCHANGED`.
- [x] Same document content creates no additional version.
- [x] Changed meaningful content returns `UPDATED`.
- [x] Changed meaningful content creates exactly one new version.
- [x] Reprocessing the changed content returns `UNCHANGED`.
- [x] Same `source_id` and `canonical_url` maps to the same document.
- [x] Different canonical URLs under the same source create separate documents.
- [x] Same canonical URL under different sources creates separate documents.

## Idempotency

- [x] Processing the exact same parsed document 10 times leaves 1 document and 1 version.
- [x] Processing one changed parsed document 10 times after that leaves 1 document and 2 versions.

## Hash Semantics

- [x] Hash excludes parser URL metadata.
- [x] Hash changes when title changes.
- [x] Hash changes when normalized text changes.
- [x] Hash uses deterministic canonical content.

## Transactions And Concurrency

- [x] Failed version insertion rolls back the document insert.
- [x] Two concurrent first ingestions converge to one document and one version.
- [x] Database uniqueness enforces `(source_id, canonical_url)`.
- [x] Database uniqueness enforces `(document_id, content_hash)` for versions.

## Static Analysis

- [x] `pytest --cov=app --cov-report=term-missing` passes.
- [x] `ruff` passes.
- [x] `mypy` passes.

## Validation Results

- `pytest`: 28 passed.
- App coverage: 93%.
- `ruff`: all checks passed.
- `mypy`: no issues found in 32 source files.

## Current Weak Assumptions

- Exact hash equality is treated as the definition of unchanged content.
- Parser-output noise can still cause false updates.
- Concurrency validation uses SQLite locally; PostgreSQL-specific locking/upsert behavior still needs validation when the real database environment is introduced.
- Alembic migrations are not implemented yet because the project does not yet have a runnable PostgreSQL migration workflow.

## Explicitly Deferred

- `index_events`
- fuzzy matching
- semantic diffing
- Redis locks
- queues
- distributed worker ordering
- search indexes

