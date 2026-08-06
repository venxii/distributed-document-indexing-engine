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

### Indexer

Computes hashes, detects changes, performs idempotent updates, and later records versions if needed.

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
