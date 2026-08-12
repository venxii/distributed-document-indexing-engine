# Phase 5C Query Performance Review

Phase 5C measures the REST query API before adding more infrastructure or search features.

## Problem Being Solved

Phase 5B introduced a working REST API, but its performance assumptions were still unvalidated:

- `ILIKE` search is acceptable for the current corpus size.
- Offset pagination is acceptable initially.
- API overhead is not the bottleneck.
- Redis, Elasticsearch, and PostgreSQL full-text search are not yet justified.

The goal of Phase 5C is to replace those assumptions with measurements.

## Possible Approaches

- Add Redis cache immediately.
- Add Elasticsearch/OpenSearch immediately.
- Add PostgreSQL full-text search immediately.
- Benchmark the existing DB and API query behavior first.

## Chosen Approach

Benchmark current behavior first.

Implemented tooling:

```text
scripts/seed_benchmark_data.py
scripts/benchmark_queries.py
```

The benchmark measures the same scenarios in two layers:

```text
SQLAlchemy query service directly
FastAPI endpoint over HTTP
```

This separates database/query cost from API serialization and HTTP overhead.

## Benchmark Setup

Environment:

- Local Docker PostgreSQL.
- Local FastAPI/Uvicorn server.
- 10 sources.
- Synthetic deterministic documents.
- 30 measured iterations per scenario.
- 5 warmup iterations per scenario.

Dataset sizes:

```text
100 documents
1,000 documents
10,000 documents
```

Scenarios:

```text
GET /documents?limit=25&offset=0
GET /documents?limit=25&offset=1000
GET /documents?source_id=...
GET /documents?q=engineer
GET /documents?q=rareterm
GET /documents?q=engineer&source_id=...
GET /sources
GET /sources/{source_id}/documents
```

## Results Summary

### 100 Documents

| Scenario | DB p50 ms | API p50 ms |
| --- | ---: | ---: |
| documents first page | 1.66 | 2.36 |
| documents source filter | 1.38 | 2.21 |
| search common term | 1.66 | 2.29 |
| search rare term | 1.79 | 2.63 |

At 100 documents, all queries are effectively small.

### 1,000 Documents

| Scenario | DB p50 ms | API p50 ms |
| --- | ---: | ---: |
| documents first page | 1.79 | 2.83 |
| documents source filter | 1.60 | 2.57 |
| search common term | 2.69 | 3.74 |
| search rare term | 4.90 | 6.05 |

At 1,000 documents, search begins separating from ordinary list/filter queries.

### 10,000 Documents

| Scenario | DB p50 ms | API p50 ms | API p95 ms |
| --- | ---: | ---: | ---: |
| documents first page | 3.84 | 4.77 | 5.74 |
| documents offset 1000 | 5.48 | 6.09 | 6.70 |
| documents source filter | 1.94 | 2.84 | 3.12 |
| search common term | 9.63 | 10.68 | 12.18 |
| search rare term | 32.53 | 34.31 | 37.28 |
| search plus source filter | 2.91 | 3.92 | 5.59 |
| sources list | 1.18 | 2.16 | 2.41 |
| source documents | 1.63 | 4.12 | 4.68 |

## Findings

API overhead is modest. Most API timings are only about 1-2 ms above direct query service timings.

Ordinary listing, source filtering, and source document queries are fast at 10,000 documents.

Offset pagination at `offset=1000` is not currently a serious bottleneck.

Text search is the clear weak path. `ILIKE '%term%'` grows faster than ordinary filtering, especially when the term requires scanning many rows before count and page results are known.

Adding a source filter materially improves text search because it narrows the candidate set before matching text.

## Why Alternatives Are Still Rejected

Redis:
Still rejected. The benchmark shows query work is mostly database-side text matching, not repeated expensive reads that a cache would clearly solve.

Elasticsearch/OpenSearch:
Still rejected. The corpus is small enough that PostgreSQL remains viable, and we have not introduced ranking or sophisticated relevance requirements.

Keyset pagination:
Still rejected. Offset pagination at the tested offsets is acceptable.

Immediate PostgreSQL full-text search:
Not implemented in Phase 5C because the goal was measurement. It is now the strongest candidate for a future improvement if we choose one.

## Tradeoffs

Synthetic data gives controlled measurements but does not perfectly represent real career-page text.

Local Docker results are useful for comparing query shapes, but they are not production capacity numbers.

The benchmark currently measures single-request latency, not concurrent API load.

The result set includes `total`, so each list endpoint performs both a count query and a page query. This is simple for clients but may become expensive at larger scale.

## Failure Cases

- Real pages may contain longer text, changing `ILIKE` behavior.
- Higher offsets than 1,000 may expose pagination costs not shown here.
- Concurrent clients may reveal connection pool or database saturation behavior.
- Counts may become expensive as data grows.
- Local machine performance may differ from EC2.

## How This Scales

The next scaling path should be evidence-driven:

1. Keep current REST API for ordinary listing/filtering.
2. If improving search is worth another phase, add PostgreSQL full-text search or trigram indexes and compare against the Phase 5C baseline.
3. Consider keyset pagination only after measuring high-offset pain.
4. Consider Redis only after observing repeated expensive read queries.
5. Consider Elasticsearch/OpenSearch only after PostgreSQL search cannot meet requirements.

## Recommendation

IndexFlow does not need Redis, Elasticsearch, or keyset pagination yet.

The only justified next engineering improvement would be a narrow PostgreSQL search-indexing experiment:

```text
current ILIKE baseline
        ↓
PostgreSQL FTS or trigram index
        ↓
compare latency and query behavior
```

That phase is optional. If the goal is a complete resume-ready backend project, IndexFlow is already strong enough after Phase 5C. If the goal is one more database-focused improvement, PostgreSQL search indexing is the most defensible next step.

## Weakest Assumption

The weakest part of the current design is that benchmark documents are synthetic and shorter than many real career pages.

This should not be fixed with new infrastructure now. If we continue, the right fix is to benchmark with real parsed pages or longer seeded document bodies before choosing a search upgrade.

## SDE Competency Check

This phase demonstrates:

- Performance measurement before optimization.
- DB-vs-API latency separation.
- Evidence-based rejection of Redis and Elasticsearch.
- Understanding of substring search limitations.
- Pagination tradeoff reasoning.
- Measured scaling behavior across corpus sizes.
