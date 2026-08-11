# Phase 3 Review Checklist

Phase 3 is not considered architecturally validated until these checks are complete.

## Parser Scope

- [x] Parser converts HTML into one internal document schema.
- [x] Parser extracts canonical URL.
- [x] Parser extracts title.
- [x] Parser extracts headings.
- [x] Parser extracts normalized text.
- [x] Parser rejects empty content.
- [x] Parser rejects non-HTML content types.
- [x] Parser rejects pages with too little meaningful text.
- [x] Parser does not compute hashes.
- [x] Parser does not write to the database.
- [x] Parser does not extract job records.

## Validation

- [x] Unit tests cover canonical URL resolution.
- [x] Unit tests cover title extraction.
- [x] Unit tests cover malformed HTML.
- [x] Unit tests cover non-HTML rejection.
- [x] Unit tests cover whitespace normalization.
- [x] Unit tests cover deterministic structured output for identical input.
- [x] Unit tests cover formatting-invariant normalized text for hash readiness.
- [x] Real career pages parsed successfully.

## Static Analysis

- [x] `ruff` passes.
- [x] `mypy` passes.
- [x] `pytest --cov` evaluated after Phase 3.

## Interview Readiness

- [x] Can explain why the parser emits page-level documents instead of job records.
- [x] Can explain why BeautifulSoup is sufficient for Phase 3.
- [x] Can explain why parser output is normalized before hashing.
- [x] Can explain why aggressive boilerplate removal is delayed.

## Current Weak Assumptions

- Main page text is enough for the next phase's hash-based change detection.
- Boilerplate text will not dominate the normalized document too badly.
- Page-level indexing is sufficient before structured job extraction.
- Static HTML contains enough useful content for the target pages.

## Validation Notes

Latest validation results:

- `pytest`: 16 passed.
- `ruff`: all checks passed.
- `mypy`: no issues found in 28 source files.
- App coverage: 79%.
- Static parser validation passed.
- Real career page parser smoke: 6 of 6 parsed successfully.
- Determinism validation passed: repeated parsing of identical HTML produced equivalent `ParsedDocument` output.
- Hash-readiness validation passed: equivalent visible content with different HTML spacing produced identical normalized text.

Real parser smoke output:

- GitHub Careers: title `GitHub Careers`, canonical `https://www.github.careers/careers-home`, text length 6278, headings 14.
- Vercel Careers: title `Careers – Vercel`, canonical `https://vercel.com/careers`, text length 5455, headings 14.
- Stripe Careers: title `Stripe Careers | Shape the Future of the Global Economy`, canonical `https://stripe.com/in/careers`, text length 6493, headings 17.
- Cloudflare Careers: title `Cloudflare Careers | Cloudflare`, canonical `https://www.cloudflare.com/careers/`, text length 5358, headings 16.
- Amazon Jobs: title `Amazon's global career site`, canonical `https://www.amazon.jobs/en/`, text length 1132, headings 2.
- Netflix Jobs: title `Join Us | Careers at Netflix`, canonical `https://jobs.netflix.com/`, text length 116, headings 0.

Netflix is the weakest parser result. It still returns a valid page-level document, but the low text length and missing headings suggest static HTML may be sparse. This is evidence to revisit Playwright later only if sparse static output hurts indexing quality.
