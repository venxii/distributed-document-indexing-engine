import argparse
import json
import statistics
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

import httpx
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.db.models import Document, Source
from app.search.documents import DocumentQuery, DocumentQueryService, DocumentSort, SortOrder
from app.search.sources import SourceQuery, SourceQueryService


@dataclass(frozen=True)
class Measurement:
    name: str
    path: str
    layer: str
    iterations: int
    p50_ms: float
    p95_ms: float
    min_ms: float
    max_ms: float
    rows_returned: int
    total: int | None


@dataclass(frozen=True)
class Scenario:
    name: str
    path: str
    db_call: Callable[[Session], tuple[int, int | None]]


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark DB and API document query behavior.")
    parser.add_argument("--database-url", default=settings.database_url)
    parser.add_argument("--api-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    engine = create_engine(args.database_url, pool_pre_ping=True)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    with session_factory() as session:
        source_id = session.scalar(select(Source.id).order_by(Source.name.asc()))
        document_count = session.scalar(select(func.count()).select_from(Document)) or 0
        if source_id is None or document_count == 0:
            raise RuntimeError("Seed benchmark data before running benchmarks.")

    scenarios = build_scenarios(source_id)
    measurements: list[Measurement] = []
    for scenario in scenarios:
        measurements.append(
            measure_db_scenario(session_factory, scenario, args.iterations, args.warmup),
        )

    with httpx.Client(base_url=args.api_base_url, timeout=30.0) as client:
        for scenario in scenarios:
            measurements.append(
                measure_api_scenario(client, scenario, args.iterations, args.warmup),
            )

    engine.dispose()

    if args.json:
        print(json.dumps([asdict(measurement) for measurement in measurements], indent=2))
    else:
        print_markdown(measurements)


def build_scenarios(source_id: Any) -> list[Scenario]:
    return [
        Scenario(
            name="documents_first_page",
            path="/documents?limit=25&offset=0",
            db_call=lambda session: documents(
                session,
                DocumentQuery(limit=25, offset=0),
            ),
        ),
        Scenario(
            name="documents_large_offset",
            path="/documents?limit=25&offset=1000",
            db_call=lambda session: documents(
                session,
                DocumentQuery(limit=25, offset=1000),
            ),
        ),
        Scenario(
            name="documents_source_filter",
            path=f"/documents?source_id={source_id}&limit=25&offset=0",
            db_call=lambda session: documents(
                session,
                DocumentQuery(source_id=source_id, limit=25, offset=0),
            ),
        ),
        Scenario(
            name="documents_search_common",
            path="/documents?q=engineer&limit=25&offset=0",
            db_call=lambda session: documents(
                session,
                DocumentQuery(q="engineer", limit=25, offset=0),
            ),
        ),
        Scenario(
            name="documents_search_rare",
            path="/documents?q=rareterm&limit=25&offset=0",
            db_call=lambda session: documents(
                session,
                DocumentQuery(q="rareterm", limit=25, offset=0),
            ),
        ),
        Scenario(
            name="documents_search_and_source",
            path=f"/documents?q=engineer&source_id={source_id}&limit=25&offset=0",
            db_call=lambda session: documents(
                session,
                DocumentQuery(q="engineer", source_id=source_id, limit=25, offset=0),
            ),
        ),
        Scenario(
            name="sources_list",
            path="/sources?limit=25&offset=0",
            db_call=lambda session: sources(
                session,
                SourceQuery(limit=25, offset=0),
            ),
        ),
        Scenario(
            name="source_documents",
            path=f"/sources/{source_id}/documents?limit=25&offset=0",
            db_call=lambda session: documents(
                session,
                DocumentQuery(
                    source_id=source_id,
                    sort=DocumentSort.last_changed_at,
                    order=SortOrder.desc,
                    limit=25,
                    offset=0,
                ),
            ),
        ),
    ]


def documents(session: Session, query: DocumentQuery) -> tuple[int, int | None]:
    result = DocumentQueryService(session).list_documents(query)
    return len(result.items), result.total


def sources(session: Session, query: SourceQuery) -> tuple[int, int | None]:
    result = SourceQueryService(session).list_sources(query)
    return len(result.items), result.total


def measure_db_scenario(
    session_factory: sessionmaker[Session],
    scenario: Scenario,
    iterations: int,
    warmup: int,
) -> Measurement:
    def run_once() -> tuple[int, int | None]:
        with session_factory() as session:
            return scenario.db_call(session)

    return measure("db", scenario, run_once, iterations, warmup)


def measure_api_scenario(
    client: httpx.Client,
    scenario: Scenario,
    iterations: int,
    warmup: int,
) -> Measurement:
    def run_once() -> tuple[int, int | None]:
        response = client.get(scenario.path)
        response.raise_for_status()
        payload = response.json()
        return len(payload.get("items", [])), payload.get("total")

    return measure("api", scenario, run_once, iterations, warmup)


def measure(
    layer: str,
    scenario: Scenario,
    run_once: Callable[[], tuple[int, int | None]],
    iterations: int,
    warmup: int,
) -> Measurement:
    for _ in range(warmup):
        run_once()

    durations_ms: list[float] = []
    rows_returned = 0
    total: int | None = None
    for _ in range(iterations):
        start = time.perf_counter()
        rows_returned, total = run_once()
        durations_ms.append((time.perf_counter() - start) * 1000)

    return Measurement(
        name=scenario.name,
        path=scenario.path,
        layer=layer,
        iterations=iterations,
        p50_ms=round(statistics.median(durations_ms), 2),
        p95_ms=round(percentile(durations_ms, 95), 2),
        min_ms=round(min(durations_ms), 2),
        max_ms=round(max(durations_ms), 2),
        rows_returned=rows_returned,
        total=total,
    )


def percentile(values: list[float], percentile_value: int) -> float:
    if not values:
        raise ValueError("cannot compute percentile of empty values")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((percentile_value / 100) * (len(ordered) - 1))))
    return ordered[index]


def print_markdown(measurements: list[Measurement]) -> None:
    print("| Scenario | Layer | p50 ms | p95 ms | Rows | Total | Path |")
    print("| --- | --- | ---: | ---: | ---: | ---: | --- |")
    for measurement in measurements:
        print(
            f"| {measurement.name} | {measurement.layer} | {measurement.p50_ms:.2f} | "
            f"{measurement.p95_ms:.2f} | {measurement.rows_returned} | "
            f"{measurement.total if measurement.total is not None else ''} | "
            f"`{measurement.path}` |",
        )


if __name__ == "__main__":
    main()
