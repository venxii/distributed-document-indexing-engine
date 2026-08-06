# Phase 2 Review Checklist

Phase 2 is not considered architecturally validated until these checks are complete.

## Functional Smoke Test

- [x] Tested against at least 5 real career pages.
- [x] Verified robots.txt is checked.
- [x] Verified request rate limiting is exercised.
- [x] Verified successful pages return HTML.
- [x] Verified redirects are handled correctly.

## Retry Validation

- [x] Verified retry behavior for real or simulated HTTP 500.
- [x] Verified retry behavior for real or simulated HTTP 429.
- [x] Verified timeout behavior.
- [x] Verified crawler stops retrying on 404.
- [x] Verified failure reason is preserved.

## Idempotency

- [x] Repeated crawls of the same stable URL produce identical stable result fields.
- [x] No duplicated metadata is produced by the crawler itself.
- [x] No resource leaks are observed in repeated crawls.

## Concurrency

- [x] 50 concurrent fetches complete successfully.
- [x] Fetches actually overlap when host rate limiting permits it.
- [x] One slow request does not block unrelated requests.
- [x] Per-host rate limiting still serializes requests for the same host when configured.

## Observability

- [x] Logs explain robots checks.
- [x] Logs explain fetch attempts.
- [x] Logs explain retry scheduling.
- [x] Logs explain final success or failure.

## Static Analysis

- [x] `ruff` passes.
- [x] `pytest` passes.
- [x] `mypy` evaluated before Phase 3.
- [x] Coverage evaluated before Phase 3.

## Interview Readiness

- [x] Can explain why `httpx`.
- [x] Can explain why not `aiohttp`.
- [x] Can explain why fail-open for robots.txt.
- [x] Can explain why exponential backoff.
- [x] Can explain why robots.txt is cached.
- [x] Can explain why rate limiting is per host.

## Validation Notes

Real career page smoke test passed on:

- GitHub Careers
- Vercel Careers
- Stripe Careers
- Cloudflare Careers
- Amazon Jobs
- Netflix Jobs

Public HTTP status endpoints were unreliable from this environment: `httpbin.org/status/404` returned an upstream 503 during validation. Retry semantics are therefore verified with deterministic `httpx.MockTransport` checks, while real timeout behavior was verified against an external request with an intentionally tiny timeout.

Latest validation results:

- `pytest`: 7 passed.
- `ruff`: all checks passed.
- `mypy`: no issues found in 24 source files.
- Coverage was evaluated. Overall coverage is low because several Phase 1 database modules and the standalone validation script are not unit-tested yet; crawler modules are the meaningful Phase 2 signal.
- Real career page smoke: 6 of 6 returned HTML successfully.
- Redirects observed and handled: GitHub Careers redirected to `https://www.github.careers/careers-home`; Stripe Jobs redirected to `https://stripe.com/in/careers`; Amazon Jobs redirected to `https://www.amazon.jobs/en/`.
- Robots metadata was recorded for every real career page.
- Netflix Careers had unavailable `robots.txt`, so the crawler used the documented fail-open behavior.
- Deterministic retry validation: HTTP 500 and 429 retried 3 times; HTTP 404 stopped after 1 attempt.
- Rate-limit validation: repeated same-host mock crawl recorded rate-limit delay.
- Idempotency validation: three repeated stable mock crawls produced identical stable fields.
- Concurrency validation: 50 mock fetches completed concurrently with max active requests of 50.
- Memory validation: 300 sequential mock crawls completed without obvious runaway memory growth.

## Current Weak Assumptions

- `robots.txt` loads quickly enough to check inline.
- Useful document pages return HTML.
- External pages are reasonably bounded in size.
- The crawler runs as one process, so in-process rate limiting is sufficient.
- HTTP content decoding handled by `httpx` is enough for target sites.
