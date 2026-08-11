# Architecture

## Project Name

Incremental Document Indexing Engine.

We are deliberately not calling the first version a distributed system. It is one modular backend designed for future horizontal scaling if workload demands it.

## Problem Being Solved

The system keeps a searchable index synchronized with external documents that change over time.

Career pages are the initial document source, but the core engineering problem is not job search. The core problem is:

> Efficiently discover, fetch, parse, detect changes, update indexed state, and query documents without unnecessary reprocessing.

## Current Architecture

```text
FastAPI
  |
  +-- Crawler
  |     Fetches immutable snapshots of external documents.
  |
  +-- Parser
  |     Converts heterogeneous HTML into structured internal documents.
  |
  +-- Indexer
  |     Computes content hashes and applies incremental updates.
  |
  +-- Search
  |     Exposes query behavior through REST endpoints.
  |
  +-- PostgreSQL
        Stores sources, crawl history, and indexed documents.
```

## Data Flow

```text
Source URL
  -> fetch document snapshot
  -> record crawl result
  -> parse HTML into structured document
  -> compute content hash
  -> compare with current indexed document
  -> skip unchanged content or update changed content
  -> query from PostgreSQL
```

## Initial Database Tables

### sources

Stores crawlable external document sources.

### crawl_runs

Stores each fetch attempt and its outcome. This gives us operational visibility into external failures, timeouts, HTTP status codes, and crawl duration.

### documents

Stores the current indexed representation of each document.

## Delayed Tables

### document_versions

Delayed until Phase 4. Versioning becomes useful when incremental indexing exists and we need to inspect previous indexed states.

### index_events

Delayed until there is a concrete debugging or audit need. Initial debugging can rely on logs, crawl metadata, and document state.

## Component Responsibilities

### API

Owns HTTP routes, request validation, and response formatting. It should not contain crawling, parsing, or indexing business logic directly.

### Crawler

Fetches immutable external document snapshots with timeouts, retries, robots.txt awareness, backoff, and per-host rate limiting.

The crawler does not parse HTML, compute hashes, or decide whether content changed. Its responsibility is to fetch safely and return enough metadata for later pipeline stages.

### Parser

Converts heterogeneous HTML into a consistent internal document shape.

The parser extracts canonical URL, title, headings, and normalized text. It does not infer individual jobs, compute content hashes, or write to the database.

### Indexer

Computes hashes, detects changes, performs idempotent updates, and records distinct successfully indexed content states.

### Search

Provides REST query endpoints over indexed documents.

### Database

Stores durable state and supports transactional updates.

## Scaling Path

1. Keep one modular FastAPI application.
2. Improve batching and concurrency limits.
3. Add database indexes based on observed query and update patterns.
4. Move crawling/indexing into a worker process if API responsiveness suffers.
5. Introduce Redis only if coordination, shared rate limiting, caching, or queueing becomes necessary.
6. Introduce a queue only if asynchronous processing becomes a real workload requirement.
7. Split API and workers into independently deployable services only when independent scaling is beneficial.

## Weakest Assumption

The weakest assumption is that useful career page content can be fetched with normal HTTP and parsed from static HTML.

If real target pages require JavaScript rendering, Playwright can be introduced as a targeted fallback rather than the default crawler.

## Phase 4 Incremental Indexing Design

Phase 4 introduces the indexing semantics that make the project an incremental indexing engine.

The central question is:

> Given a parsed document and the currently stored document record, can the system decide whether meaningful content changed and update storage exactly once when needed?

### Inputs

- `ParsedDocument`
- `source_id`
- Existing `documents` row, if one exists

The indexer does not crawl, parse HTML, or serve query requests.

### Data Model

The Phase 4 schema should contain:

```text
documents
- id
- source_id
- canonical_url
- title
- normalized_text
- content_hash
- first_seen_at
- last_seen_at
- last_changed_at
- is_active

document_versions
- id
- document_id
- content_hash
- title
- normalized_text
- created_at
```

`document_versions` is introduced in Phase 4 because it now solves a concrete problem: preserving each distinct successfully indexed content state so we can validate, debug, and explain incremental updates.

`index_events` remains deferred. The indexer can return `created`, `updated`, `unchanged`, or `failed` from application code and log that result. Persistent event history should be added only if operational debugging proves logs and document/version state are insufficient.

### Core Invariants

```text
Invariant 1:
(source_id, canonical_url) identifies one current document.
```

```text
Invariant 2:
content_hash represents canonical parsed content, not crawl metadata.
```

The hash must exclude:

- crawl timestamp
- HTTP status
- response headers
- robots metadata
- rate-limit metadata

```text
Invariant 3:
If the new hash equals the current hash, content is unchanged.
```

For unchanged content:

- `content_hash` stays the same
- `last_changed_at` stays the same
- no new `document_versions` row is created
- `last_seen_at` may update

```text
Invariant 4:
Document updates and version inserts are atomic.
```

The database should never commit a new current document state without the corresponding version row, or a version row without the corresponding current document state.

```text
Invariant 5:
Reprocessing the same parsed document is idempotent.
```

Repeated processing converges to the same logical database state.

### Version Semantics

A document version represents:

> A distinct successfully indexed content state of a document.

That gives the system a clean rule:

```text
same document + same content_hash
        -> no new version

same document + different content_hash
        -> exactly one new version
```

The first successful ingestion creates both:

```text
documents row
document_versions row for version 1
```

This makes the historical sequence easy to reason about:

```text
First crawl
    -> CREATED
    -> version 1

Same content later
    -> UNCHANGED
    -> no new version

Changed content later
    -> UPDATED
    -> version 2
```

### State Machine

```text
                       no existing row
ParsedDocument ─────────────────────────▶ CREATED
      │                                      │
      │                                      ▼
      │                                insert document
      │                                insert version 1
      │
      │ existing row
      ▼
compute content_hash
      │
      ├── hash equal ───────────────────▶ UNCHANGED
      │                                      │
      │                                      ▼
      │                                update last_seen_at
      │                                no new version
      │
      └── hash different ───────────────▶ UPDATED
                                             │
                                             ▼
                                       update document
                                       insert new version
```

Failures during database work should roll back the transaction and produce a failed indexing result.

### Canonical Hashing Definition

The content hash should be SHA-256 over an explicit canonical representation of the parsed document.

Proposed canonical content:

```text
title
headings
normalized_text
```

`canonical_url` should not be part of the content hash. It identifies the logical document row; it is not the document content. If a page's canonical URL changes, that is an identity-resolution problem, not a content-change problem.

Title changes should count as content changes because titles are visible document metadata and often carry meaningful page-level information.

Headings should be included even though they may appear in `normalized_text`, because they preserve document structure in a stable, explicit way. The canonicalization step must use deterministic separators so this does not become ambiguous.

Empty optional fields should be represented explicitly, for example:

```text
title:
headings:
body:
```

That avoids accidental hash ambiguity between missing and shifted fields.

Parser behavior changes can change hashes for documents even if the source page did not change. That is acceptable for now, but it must be understood: parser upgrades can trigger re-indexing. If this becomes operationally painful later, the system can add a parser version to version metadata or run controlled reindexing.

### Transaction Boundary

Each indexing operation should run in one database transaction:

1. Compute canonical content and hash outside the transaction.
2. Begin transaction.
3. Find existing `documents` row by `(source_id, canonical_url)`.
4. If no row exists, insert `documents` and insert version 1.
5. If row exists and hash matches, update only `last_seen_at`.
6. If row exists and hash differs, update `documents` and insert a new `document_versions` row.
7. Commit.

If any database step fails, roll back the entire operation.

### Race Conditions

The database must enforce document identity:

```text
UNIQUE(source_id, canonical_url)
```

This prevents two workers from creating two current rows for the same logical document.

Application code should still check for an existing row first, but correctness should not rely only on Python. The database owns the uniqueness invariant.

For future multiple workers, the indexer should use database-supported conflict handling or row locking around the current `documents` row. The exact implementation can be chosen during Phase 4 coding, but the design principle is:

> Use PostgreSQL constraints and transactions to enforce storage invariants.

### Idempotency Semantics

Processing the same parsed document repeatedly should be safe.

Expected behavior:

```text
process(document A) -> CREATED, version 1
process(document A) -> UNCHANGED, no version
process(document A) -> UNCHANGED, no version
```

If two workers process the same new document concurrently, the final state should still be:

```text
one documents row
one version row for that content hash
```

If two different content states race, the final current document should be one of the successfully committed states, with corresponding version rows that obey the distinct-hash invariant. We should not try to solve distributed ordering yet.

### Database Indexes

Required in Phase 4:

```text
UNIQUE INDEX documents_source_canonical_url_idx
ON documents (source_id, canonical_url)
```

```text
INDEX documents_source_id_idx
ON documents (source_id)
```

```text
INDEX documents_content_hash_idx
ON documents (content_hash)
```

```text
UNIQUE INDEX document_versions_document_hash_idx
ON document_versions (document_id, content_hash)
```

The unique version index enforces:

```text
same document + same content_hash -> at most one version
```

Search-specific indexes are deferred to Phase 5.

### Failure Cases

- Database insert fails after computing hash.
- Document update succeeds in application flow but version insert fails.
- Two workers process the same new document concurrently.
- Two workers process different content for the same document concurrently.
- Parser output changes after a parser code update.
- Canonical URL changes for the same real-world page.
- Two different URLs resolve to the same canonical URL.
- Hash collision occurs.
- PostgreSQL connection fails halfway through indexing.

SHA-256 collisions are theoretically possible but not a practical concern for this project. The more realistic risk is hashing noisy parser output.

### Complexity Analysis

Let:

- `n` be the canonical content size
- `m` be the number of indexed documents
- `v` be the number of versions for one document

Hashing is:

```text
O(n)
```

Document lookup by `(source_id, canonical_url)` with an index is:

```text
O(log m)
```

Unchanged update is:

```text
O(log m) lookup + O(1) row update
```

Changed update is:

```text
O(log m) lookup + O(1) document update + O(log v) version uniqueness check/insert
```

Storage growth is proportional to the number of distinct content states, not the number of crawls.

### Explicitly Deferred Problems

- Fuzzy matching
- Semantic diffing
- Job-level extraction
- Search ranking
- `index_events`
- Redis-based coordination
- Queue-based workers
- Cross-process distributed ordering
- Elasticsearch/OpenSearch
- Playwright fallback

These are deferred because exact hash-based document indexing is sufficient for the current engineering goal and is easier to test, explain, and make idempotent.

## Phase 5A PostgreSQL Validation Design

Phase 5A validates the Phase 4 storage assumptions against PostgreSQL before building the REST query API.

This is not a feature expansion. The goal is to prove that PostgreSQL enforces the invariants the indexer depends on:

- one current document per `(source_id, canonical_url)`
- one version per `(document_id, content_hash)`
- atomic document/version writes
- correct behavior under concurrent first ingestion

The detailed validation plan lives in `docs/phase-5a-postgresql-validation.md`.

Phase 5A explicitly does not introduce Redis, queues, workers, AWS deployment, external search, or new indexing semantics.
