# Architectural Decisions

## Why Incremental, Not Distributed?

Problem:
The project needs to demonstrate scalable backend engineering without pretending the first version is a distributed system.

Alternatives:
- Call it a distributed document indexing engine
- Call it an incremental document indexing engine
- Split the system into multiple services immediately

Chosen:
Call it an Incremental Document Indexing Engine.

Reason:
The current architecture is one deployable application with clear internal module boundaries. Calling it distributed would be inaccurate and weaker than explaining how it can evolve into separately deployable components later.

Tradeoffs:
The name sounds less flashy, but it is more honest and more defensible in an interview.

## Why a Single Modular Backend?

Problem:
We need crawler, parser, indexing, and query functionality, but the project is still small enough that distributed services would add unnecessary complexity.

Alternatives:
- One modular FastAPI application
- Separate crawler, indexer, and API services
- Event-driven microservices

Chosen:
One modular FastAPI application.

Reason:
It keeps deployment and debugging simple while allowing clean internal boundaries that can later be separated if needed.

Tradeoffs:
Crawler and API workloads initially share the same runtime.

## Why PostgreSQL First?

Problem:
We need persistent storage for sources, crawl history, normalized documents, and searchable indexed content.

Alternatives:
- PostgreSQL
- PostgreSQL plus Elasticsearch
- Document database
- Files plus search index

Chosen:
PostgreSQL.

Reason:
PostgreSQL handles relational metadata, transactional updates, indexes, versionable state, and basic full-text search in one reliable system.

Tradeoffs:
Search ranking and distributed search capabilities are limited compared with Elasticsearch.

## Why No Redis Initially?

Problem:
Redis could be used for caching, queues, rate limiting, or deduplication, but no concrete bottleneck exists yet.

Alternatives:
- No Redis
- Redis cache
- Redis-backed job queue
- In-memory cache

Chosen:
No Redis initially.

Reason:
Adding Redis before identifying a real need increases operational complexity without improving the core indexing design.

Tradeoffs:
If we later need distributed rate limiting, queueing, or shared cache state, we will need to introduce Redis then.

## Why No Playwright Initially?

Problem:
Some career pages may render content with JavaScript, but browser automation is heavier than plain HTTP fetching.

Alternatives:
- httpx only
- Playwright for all pages
- Playwright only as fallback

Chosen:
httpx first, Playwright only if justified later.

Reason:
Most indexing logic can be proven with simpler HTTP crawling. Playwright should solve a specific crawling failure, not be the default.

Tradeoffs:
Some JavaScript-heavy pages may not be indexable in the first crawler version.

## Why Delay Document Versions?

Problem:
Version history is useful only after the system can detect changes and needs to preserve previous indexed states.

Alternatives:
- Add document_versions from the beginning
- Never store previous versions
- Add document_versions during incremental indexing

Chosen:
Add document_versions during Phase 4.

Reason:
The table solves a real problem once content hashing and change detection exist. Before that, it adds schema and code without behavior.

Tradeoffs:
Before Phase 4, the system stores only current indexed document state.

## Why Delay Index Events?

Problem:
We want the system to be explainable, but we do not yet have enough indexing behavior to know what events are useful.

Alternatives:
- Add index_events from the beginning
- Use application logs only
- Add index_events later when indexing behavior becomes more complex

Chosen:
Delay index_events.

Reason:
The initial system can be understood through sources, crawl_runs, and documents. Adding a separate event table before real indexing complexity exists creates schema and code overhead without solving a current problem.

Tradeoffs:
Early debugging relies more on logs and crawl metadata. If indexing behavior becomes harder to explain, we will add structured index events later.

## Why Treat Crawling as Snapshot Fetching?

Problem:
The crawler needs a clear responsibility that supports incremental indexing without absorbing parser or indexer logic.

Alternatives:
- Let the crawler fetch, parse, and detect changes
- Let the crawler only fetch immutable document snapshots
- Store raw HTML snapshots immediately in S3

Chosen:
Let the crawler only fetch immutable document snapshots and crawl metadata.

Reason:
Fetching is a networking concern. Parsing and change detection are separate pipeline stages with different failure modes. Keeping the crawler narrow makes retries, robots.txt behavior, and rate limiting easier to reason about.

Tradeoffs:
Later phases must explicitly pass crawl output into parser and indexing components.

## Why Retry Only Transient Fetch Failures?

Problem:
External HTTP requests can fail temporarily, but retries can also amplify load or hide permanent failures.

Alternatives:
- Retry every failed request
- Retry no failed requests
- Retry only timeouts, network errors, HTTP 429, and 5xx responses

Chosen:
Retry only timeouts, network errors, HTTP 429, and 5xx responses.

Reason:
These failures are plausibly transient. Regular 4xx responses usually mean the request is invalid, forbidden, or missing, so retrying wastes time and creates unnecessary traffic.

Tradeoffs:
Some unusual 4xx responses may be transient, but the simpler policy is safer and easier to defend.

## Why Robots.txt Fail Open?

Problem:
The crawler should respect robots.txt, but robots.txt itself may be unavailable due to transient network or server errors.

Alternatives:
- Fail closed when robots.txt cannot be fetched
- Fail open when robots.txt cannot be fetched
- Require manual allowlists for every source

Chosen:
Fail open when robots.txt cannot be fetched, but obey explicit disallow rules when robots.txt is available.

Reason:
Many real sites do not serve robots.txt reliably. Failing open keeps the crawler useful while still respecting explicit crawl restrictions.

Tradeoffs:
This is a weaker politeness posture than failing closed. If the project later crawls sensitive or high-volume targets, this decision should be revisited.

## Why Per-Host Rate Limiting In Process?

Problem:
The crawler needs to avoid sending bursts of requests to the same host.

Alternatives:
- No rate limiting
- In-process per-host rate limiting
- Redis-backed distributed rate limiting

Chosen:
In-process per-host rate limiting.

Reason:
The current system is one process. In-process state solves the immediate politeness problem without introducing Redis before we have multiple workers.

Tradeoffs:
If multiple crawler processes are introduced later, each process will have its own rate limit state. At that point, shared coordination may justify Redis.
