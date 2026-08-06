# Scaling

## Scaling Philosophy

Scale the system by responding to observed pressure, not by adding infrastructure preemptively.

## Expected Evolution

1. Start with one modular FastAPI application.
2. Use async crawling with explicit concurrency and per-domain rate limits.
3. Add PostgreSQL indexes based on real query patterns.
4. Batch crawl and indexing work when single-document processing becomes inefficient.
5. Move crawler and indexer into a worker process if API latency suffers.
6. Add Redis only for a specific need such as shared rate limiting, queue coordination, or caching hot query results.
7. Introduce an external search engine only if PostgreSQL full-text search becomes insufficient.

## What We Are Avoiding

- Microservices before independent scaling is necessary.
- Redis before a coordination or caching problem exists.
- Elasticsearch before PostgreSQL search is measured as insufficient.
- Playwright before real pages require JavaScript rendering.
- S3 before raw snapshot replay or audit history is valuable.

