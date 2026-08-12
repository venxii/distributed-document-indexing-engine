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

## Why Search as a Documents Query Parameter?

Problem:
The REST API needs to let clients search indexed documents, but the current search behavior is simple filtering over current document rows.

Alternatives:
- `GET /documents?q=backend`
- A separate `GET /search?q=backend`
- Elasticsearch/OpenSearch
- Python-side filtering

Chosen:
Use `GET /documents?q=backend`.

Reason:
Search is currently one filter dimension on documents, alongside source filtering, sorting, and pagination. A separate search endpoint should wait until search has distinct semantics such as ranking, relevance scoring, tokenization, or a richer query language.

Tradeoffs:
The API is less flashy than a dedicated search subsystem, but it is simpler and more honest about what the system currently does.

## Why PostgreSQL-Side `ILIKE` Search First?

Problem:
Users need basic text search over indexed document titles and normalized text.

Alternatives:
- PostgreSQL `ILIKE`
- PostgreSQL full-text search
- Trigram indexes
- Elasticsearch/OpenSearch
- Python-side filtering

Chosen:
PostgreSQL-side `ILIKE`.

Reason:
It keeps filtering in the database, avoids transferring all documents into Python, and is sufficient until we measure that query latency or relevance quality is inadequate.

Tradeoffs:
`ILIKE` does not provide ranking, stemming, tokenization, or strong large-corpus performance. PostgreSQL full-text search or trigram indexes are the likely next step if Phase 5C measurements justify them.

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

## Why Parse Pages Into Document Text, Not Job Records?

Problem:
Career pages vary widely. Some expose individual jobs clearly, while others are general landing pages, embedded boards, or JavaScript-heavy pages.

Alternatives:
- Extract individual job records in Phase 3
- Normalize each fetched page into one internal document
- Build site-specific adapters for every company

Chosen:
Normalize each fetched page into one internal document with canonical URL, title, headings, and normalized text.

Reason:
The project is an indexing engine, not a job portal. Page-level document parsing directly supports Phase 4 hash-based change detection and avoids pretending we can accurately extract job entities from arbitrary HTML without more evidence.

Tradeoffs:
The system cannot yet answer structured job questions such as location or department. That is acceptable because the current goal is reliable document indexing.

## Why BeautifulSoup for Phase 3 Parsing?

Problem:
We need to parse messy external HTML into a stable internal document representation.

Alternatives:
- BeautifulSoup
- lxml directly
- Browser DOM extraction with Playwright
- Site-specific parsers

Chosen:
BeautifulSoup.

Reason:
BeautifulSoup is simple, forgiving of malformed HTML, and sufficient for extracting page-level text, titles, headings, and canonical URLs.

Tradeoffs:
It does not execute JavaScript and may preserve some boilerplate text. If real pages require browser-rendered DOM content, Playwright can be introduced as a targeted fallback later.

## Why Normalize Whitespace and Remove Script-Like Tags?

Problem:
Raw HTML contains formatting noise, scripts, styles, and markup differences that should not make the internal document unstable.

Alternatives:
- Store raw HTML as the parser output
- Normalize only basic text extraction
- Remove non-content tags and normalize whitespace

Chosen:
Remove script-like non-content tags and normalize text whitespace into stable lines.

Reason:
Phase 4 will use exact content hashes. The parser should reduce irrelevant formatting noise before hashing without attempting fuzzy matching or semantic interpretation.

Tradeoffs:
The parser may still include navigation or footer text, and aggressive cleanup could remove useful context if taken too far. The current cleanup is intentionally conservative.

## Why Exact Hash-Based Change Detection?

Problem:
The indexer needs to decide whether a parsed document changed without reprocessing unchanged content.

Alternatives:
- Exact hash comparison
- Fuzzy text similarity
- Semantic diffing
- Always re-index

Chosen:
Exact hash comparison over canonical parsed content.

Reason:
Exact hashing is deterministic, fast, simple to test, and easy to explain. It directly supports idempotency: same canonical content produces the same hash and therefore no new version.

Tradeoffs:
Small parser-output changes can trigger updates even if the human-meaningful page content did not change. We accept this for Phase 4 because fuzzy matching would introduce subjective thresholds and harder-to-debug behavior.

## Why SHA-256 for Content Hashing?

Problem:
The system needs a stable digest for canonical parsed content.

Alternatives:
- SHA-256
- MD5
- Python built-in `hash`
- Store and compare full text only

Chosen:
SHA-256.

Reason:
SHA-256 is deterministic across processes, widely understood, collision-resistant for practical purposes, and available in Python's standard library.

Tradeoffs:
It is more computationally expensive than non-cryptographic hashes, but the cost is linear in document size and negligible compared with network crawling and database I/O for this project.

## Why Exclude Canonical URL From the Content Hash?

Problem:
The indexer must distinguish document identity from document content.

Alternatives:
- Include canonical URL in the hash
- Exclude canonical URL from the hash

Chosen:
Exclude canonical URL from the content hash.

Reason:
`canonical_url` identifies the logical document row through `(source_id, canonical_url)`. It is not content. A URL identity change should be handled as an identity/canonicalization issue rather than as a content mutation.

Tradeoffs:
If a page changes only its canonical URL while keeping identical visible content, the system may treat it as a different logical document. That is acceptable for now because URL identity resolution is separate from content change detection.

## Why Include Title and Headings in the Canonical Content?

Problem:
The hash must represent meaningful parsed document content.

Alternatives:
- Hash only `normalized_text`
- Hash `title`, `headings`, and `normalized_text`
- Hash every parser field including URL metadata

Chosen:
Hash `title`, `headings`, and `normalized_text`.

Reason:
Titles and headings are visible document structure and can change meaningfully even when body text is similar. Including them keeps page-level document identity closer to what a user or interviewer would understand as the document's content.

Tradeoffs:
Headings may also appear in `normalized_text`, so this can duplicate some information. Deterministic field separators make the representation unambiguous, and the simplicity is worth it.

## Why Add Document Versions in Phase 4?

Problem:
Incremental indexing needs to prove which distinct content states have been successfully indexed over time.

Alternatives:
- Keep only the current `documents` row
- Add `document_versions`
- Add a general `index_events` audit table

Chosen:
Add `document_versions`.

Reason:
A version now solves a concrete Phase 4 problem: preserving each distinct successfully indexed content state. It lets us verify that unchanged content does not create duplicate versions and changed content creates exactly one new version.

Tradeoffs:
Version history increases storage usage. Storage grows with distinct content states, not crawl count, which is acceptable for this phase.

## Why First Ingestion Creates a Version?

Problem:
The system needs clear version semantics from the first successful index operation onward.

Alternatives:
- Create a current document row only on first ingestion
- Create both a current document row and version 1

Chosen:
Create both a current document row and version 1.

Reason:
This gives a simple invariant: every successfully indexed content state has a version row, including the initial state.

Tradeoffs:
The first ingestion does one extra insert, but the resulting model is easier to reason about and test.

## Why No Index Events in Phase 4?

Problem:
The indexer can produce outcomes such as `created`, `updated`, `unchanged`, and `failed`.

Alternatives:
- Store every outcome in an `index_events` table
- Return the outcome from the indexing service and log it
- Store only failures persistently

Chosen:
Return the outcome from the indexing service and log it.

Reason:
The current database state plus `document_versions` is enough to explain content history. A general event table would add schema and write complexity before we have evidence that persistent event history is needed.

Tradeoffs:
Operational debugging relies on logs for per-attempt outcome history. If that becomes insufficient, `index_events` can be introduced with evidence.

## Why Use Database Constraints for Document Identity?

Problem:
Multiple indexing attempts may process the same logical document concurrently.

Alternatives:
- Rely only on application-level existence checks
- Enforce uniqueness in PostgreSQL with `(source_id, canonical_url)`
- Add distributed locks

Chosen:
Enforce uniqueness in PostgreSQL with `(source_id, canonical_url)`.

Reason:
Document identity is a storage invariant, so the database should enforce it. Application checks are useful for control flow, but they are not enough under concurrency.

Tradeoffs:
The indexer must handle uniqueness conflicts or use upsert/locking behavior carefully. That is simpler than introducing distributed locking before multiple workers exist.

## Why Defer Redis or a Queue for Indexing?

Problem:
Future multiple workers may need coordination, but Phase 4 is still inside one modular backend.

Alternatives:
- Add Redis locks now
- Add a queue now
- Use PostgreSQL transactions and constraints first

Chosen:
Use PostgreSQL transactions and constraints first.

Reason:
The current observed problem is idempotent database updates, not distributed coordination. PostgreSQL already gives us transactions, uniqueness constraints, and row-level concurrency tools.

Tradeoffs:
If we later run many independent workers and see coordination bottlenecks, Redis or a queue may become justified. Adding them now would be premature.

## Why Validate PostgreSQL Before Building the REST API?

Problem:
Phase 4 indexing correctness depends on database constraints, transactions, and concurrent write behavior that SQLite cannot fully validate.

Alternatives:
- Move directly to REST API development
- Add Redis or another coordination system
- Validate the existing indexing design against PostgreSQL first

Chosen:
Validate the existing indexing design against PostgreSQL first.

Reason:
PostgreSQL is the storage system the project is designed around. Before exposing indexed documents through an API, we should verify that the database enforces the invariants the indexer relies on.

Tradeoffs:
This delays API work, but it reduces the risk of building query behavior on top of unvalidated storage assumptions.

## Why PostgreSQL Validation Is Not a New Architecture Layer?

Problem:
Adding Docker Compose and PostgreSQL could be mistaken for adding technology for resume optics.

Alternatives:
- Treat PostgreSQL validation as a feature phase
- Treat PostgreSQL validation as infrastructure validation
- Skip it until deployment

Chosen:
Treat PostgreSQL validation as infrastructure validation.

Reason:
The project already chose PostgreSQL as the durable store. Phase 5A simply verifies that the implemented indexing logic behaves correctly against that chosen dependency.

Tradeoffs:
It adds local environment setup, but that setup directly supports correctness validation rather than architectural breadth.

## Why Benchmark Before Adding Search Infrastructure?

Problem:
The REST API uses simple PostgreSQL queries, including `ILIKE` for text search, but we did not know whether search, pagination, API overhead, or database filtering was the real bottleneck.

Alternatives:
- Add Redis
- Add Elasticsearch/OpenSearch
- Add PostgreSQL full-text search immediately
- Measure the current DB and API behavior first

Chosen:
Measure current behavior first.

Reason:
Benchmarking showed that ordinary listing/filtering remained fast at 10,000 documents, API overhead was modest, and text search was the weak path. This gives us evidence for the next decision instead of adding infrastructure by guesswork.

Tradeoffs:
Benchmarking takes time and synthetic data is imperfect, but it prevents premature architecture changes.

## Why Not Add Redis After Phase 5C?

Problem:
Redis could cache repeated API reads, but Phase 5C needed to identify whether repeated reads were actually the problem.

Alternatives:
- Add Redis cache
- Improve database queries/search first
- Keep current architecture

Chosen:
Do not add Redis after Phase 5C.

Reason:
The benchmark points to database-side text matching as the expensive path, not repeated identical reads. Redis would add operational complexity without addressing the measured bottleneck directly.

Tradeoffs:
Some repeated queries could still benefit from caching later, but that should be based on observed traffic patterns.
