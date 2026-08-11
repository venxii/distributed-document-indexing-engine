# Future Work

Future work should be added only when it solves a real problem observed in the system.

## Candidates

- `index_events` for detailed auditability if indexing decisions become hard to debug.
- Redis for shared rate limiting, queueing, or caching hot query results.
- Playwright fallback for JavaScript-rendered pages.
- Parser quality scoring if sparse static HTML becomes a recurring issue.
- S3 snapshot storage if raw HTML replay becomes valuable.
- External search if PostgreSQL full-text search is measured as insufficient.
- Separate worker process if crawling or indexing affects API responsiveness.
