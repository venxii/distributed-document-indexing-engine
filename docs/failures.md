# Failure Cases

## External Fetch Failures

- DNS failure
- TLS failure
- HTTP timeout
- 429 rate limiting
- 403 bot protection
- 500-class upstream error
- robots.txt disallowing access
- robots.txt unavailable
- too many redirects

## Parsing Failures

- HTML structure changes
- Useful content is rendered only by JavaScript
- Parser extracts navigation or boilerplate instead of main content
- Parser removes meaningful text during cleanup

## Indexing Failures

- Hash changes due to irrelevant formatting noise
- Hash does not change despite meaningful content changes because parsing is too lossy
- Duplicate documents appear under different URLs
- Database write fails during update
- Repeated crawl retries create duplicate state

## Operational Failures

- API latency increases during crawl bursts
- Database connection pool exhaustion
- Slow queries over growing indexed content
- Crawl schedules become too aggressive for target domains
