# Incremental Document Indexing Engine

A backend engineering project focused on efficiently keeping a searchable index synchronized with external documents that change over time.

The documents currently happen to be software company career pages, but this is not designed as a job portal. The core problem is an indexing pipeline:

```text
Source URL -> Crawler -> Parser -> Content Hash -> Change Detection -> PostgreSQL Index -> Query API
```

The system starts as one modular FastAPI application. It is designed with clear module boundaries so that the crawler, indexing pipeline, and query API can later be separated into independently deployable services if workload demands it.

## Engineering Philosophy

- Prefer simple designs that solve current problems.
- Avoid technologies that do not have a clear job.
- Keep module boundaries clean before introducing service boundaries.
- Optimize for maintainability, reliability, scalability, and interview explainability.

## Current Phase

Phase 3: Parser.

The crawler fetches immutable external document snapshots with timeouts, retry/backoff, robots.txt awareness, and per-host rate limiting.

The parser converts fetched HTML into an internal document schema with canonical URL, title, headings, and normalized text.

Indexing, cache, and deployment implementation are intentionally delayed until later phases.
