# ruff: noqa: E402

"""Measure Phase 3 import and module response budgets on a local CSV.

The upload transfer is intentionally excluded: import timing starts with the
CSV already on disk and measures ``ingest_csv`` (validation plus derived facts).
The API measurements use a fresh in-process TestClient and bearer token.
"""

import argparse
import hashlib
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

# Allow the documented root-level command to import the backend package.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import duckdb
from app.auth import get_now
from app.config import Settings, get_settings
from app.ingest import CreatedDataset, ingest_csv
from app.main import app
from app.response_cache import ResponseCache, get_response_cache
from fastapi.testclient import TestClient

IMPORT_BUDGET = 30.0
UNCACHED_BUDGET = 3.0
CACHED_BUDGET = 1.0
FIXED_NOW = datetime(2026, 1, 1, tzinfo=UTC)


@dataclass(frozen=True)
class Measurement:
    operation: str
    scenario: str
    cache_state: str
    seconds: float
    budget: float
    response_sha256: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "scenario": self.scenario,
            "cache": self.cache_state,
            "seconds": self.seconds,
            "budget_seconds": self.budget,
            "within_budget": self.seconds <= self.budget,
            "response_sha256": self.response_sha256,
        }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_sha() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _ram_bytes() -> int | None:
    try:
        import resource

        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(value * 1024) if sys.platform != "darwin" else int(value)
    except (ImportError, AttributeError):
        return None


def _cpu_model() -> str:
    if sys.platform == "linux":
        try:
            for line in Path("/proc/cpuinfo").read_text().splitlines():
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
        except OSError:
            pass
    return platform.processor() or "unknown"


def _scenario_params(first: date, last: date) -> list[tuple[str, dict[str, str]]]:
    ninety_start = last - timedelta(days=89)
    return [
        ("full_previous_period", {}),
        ("full_previous_year", {"comparison": "previous_year"}),
        (
            "last_90_days_previous_period",
            {"start": ninety_start.isoformat(), "end": last.isoformat()},
        ),
    ]


def _request(
    client: TestClient,
    dataset: CreatedDataset,
    path: str,
    params: dict[str, str],
) -> tuple[float, bytes]:
    started = time.perf_counter()
    response = client.get(
        f"/api/datasets/{dataset.dataset_id}{path}",
        params=params,
        headers={"Authorization": f"Bearer {dataset.token}"},
    )
    seconds = time.perf_counter() - started
    if response.status_code != 200:
        raise RuntimeError(f"{path} returned HTTP {response.status_code}: {response.text}")
    return seconds, response.content


def _measure_module(
    client: TestClient,
    cache: ResponseCache,
    dataset: CreatedDataset,
    operation: str,
    path: str,
    params: dict[str, str],
    scenario: str,
) -> list[Measurement]:
    cache.clear()
    uncached_seconds, body = _request(client, dataset, path, params)
    cached_seconds, cached_body = _request(client, dataset, path, params)
    digest = _sha256(body)
    if cached_body != body:
        raise RuntimeError(f"cached {operation} response differs from uncached response")
    return [
        Measurement(operation, scenario, "uncached", uncached_seconds, UNCACHED_BUDGET, digest),
        Measurement(operation, scenario, "cached", cached_seconds, CACHED_BUDGET, digest),
    ]


def _import_dataset(input_path: Path, settings: Settings, run: int) -> CreatedDataset:
    staged = settings.dataset_dir / "uploads" / f"benchmark-{run}.csv"
    staged.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(input_path, staged)
    result = ingest_csv(staged, "USD", settings, FIXED_NOW)
    if not isinstance(result, CreatedDataset):
        raise RuntimeError(f"benchmark input failed validation: {result.to_dict()}")
    return result


def run_benchmark(input_path: Path, runs: int) -> dict[str, Any]:
    input_bytes = input_path.read_bytes()
    input_sha = _sha256(input_bytes)
    measurements: list[Measurement] = []
    import_seconds: list[float] = []
    with tempfile.TemporaryDirectory(prefix="osa-benchmark-") as temporary:
        settings = Settings(DATASET_DIR=Path(temporary) / "datasets")
        cache = ResponseCache(
            max_entries=settings.response_cache_max_entries,
            ttl_seconds=settings.response_cache_ttl_seconds,
        )
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_now] = lambda: FIXED_NOW
        app.dependency_overrides[get_response_cache] = lambda: cache
        try:
            with TestClient(app) as client:
                datasets: list[CreatedDataset] = []
                for run in range(runs):
                    started = time.perf_counter()
                    datasets.append(_import_dataset(input_path, settings, run))
                    import_seconds.append(time.perf_counter() - started)

                for dataset in datasets:
                    first = date.fromisoformat(dataset.meta["date_range"]["min"])
                    last = date.fromisoformat(dataset.meta["date_range"]["max"])
                    scenarios = _scenario_params(first, last)
                    discovery_params = {"start": first.isoformat(), "end": last.isoformat()}
                    _, discovery_body = _request(client, dataset, "/products", discovery_params)
                    top = json.loads(discovery_body)["rankings"]["by_gross_sales"][0]
                    product_id = top["product_id"]
                    for scenario, params in scenarios:
                        measurements.extend(
                            _measure_module(
                                client, cache, dataset, "Overview", "/overview", params, scenario
                            )
                        )
                        measurements.extend(
                            _measure_module(
                                client, cache, dataset, "Products", "/products", params, scenario
                            )
                        )
                        detail_params = {**params, "product_id": product_id}
                        measurements.extend(
                            _measure_module(
                                client,
                                cache,
                                dataset,
                                "Product detail",
                                "/products/detail",
                                detail_params,
                                scenario,
                            )
                        )
                        measurements.extend(
                            _measure_module(
                                client, cache, dataset, "Customers", "/customers", params, scenario
                            )
                        )
                        # Projection is served by the customers endpoint after #132.
                        measurements.extend(
                            _measure_module(
                                client,
                                cache,
                                dataset,
                                "Projection",
                                "/customers",
                                params,
                                scenario,
                            )
                        )
        finally:
            app.dependency_overrides.clear()

    environment = {
        "git_commit": _git_sha(),
        "cpu_model": _cpu_model(),
        "logical_cpus": os.cpu_count(),
        "ram_bytes": _ram_bytes(),
        "os": platform.platform(),
        "python": platform.python_version(),
        "duckdb": duckdb.__version__,
    }
    metadata = {
        "rows": sum(1 for line in input_bytes.splitlines()) - 1,
        "bytes": len(input_bytes),
        "sha256": input_sha,
    }
    table: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str, str], list[Measurement]] = {}
    for measurement in measurements:
        grouped.setdefault(
            (measurement.operation, measurement.scenario, measurement.cache_state), []
        ).append(measurement)
    for (operation, scenario, cache_state), values in grouped.items():
        seconds = [value.seconds for value in values]
        budget = values[0].budget
        table.append(
            {
                "operation": operation,
                "scenario": scenario,
                "cache": cache_state,
                "median_seconds": statistics.median(seconds),
                "min_seconds": min(seconds),
                "max_seconds": max(seconds),
                "budget_seconds": budget,
                "within_budget": statistics.median(seconds) <= budget,
                "response_sha256": values[0].response_sha256,
            }
        )

    return {
        "environment": environment,
        "input": metadata,
        "runs": runs,
        "import": {
            "operation": "validate+import",
            "samples": import_seconds,
            "median_seconds": statistics.median(import_seconds),
            "min_seconds": min(import_seconds),
            "max_seconds": max(import_seconds),
            "budget_seconds": IMPORT_BUDGET,
            "within_budget": statistics.median(import_seconds) <= IMPORT_BUDGET,
        },
        "table": table,
        "measurements": [measurement.as_dict() for measurement in measurements],
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "| Operation | Scenario | Cache | Median (s) | Min (s) | Max (s) | Budget (s) | Within budget | Response SHA-256 |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | :---: | --- |",
    ]
    import_report = report["import"]
    lines.append(
        f"| validate+import | all runs | uncached | {import_report['median_seconds']:.4f} | "
        f"{import_report['min_seconds']:.4f} | {import_report['max_seconds']:.4f} | 30.0000 | "
        f"{'yes' if import_report['within_budget'] else 'no'} | — |"
    )
    for row in report["table"]:
        lines.append(
            f"| {row['operation']} | {row['scenario']} | {row['cache']} | "
            f"{row['median_seconds']:.4f} | {row['min_seconds']:.4f} | {row['max_seconds']:.4f} | "
            f"{row['budget_seconds']:.4f} | {'yes' if row['within_budget'] else 'no'} | "
            f"{row['response_sha256']} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, required=True, help="existing benchmark CSV")
    parser.add_argument("--runs", type=int, default=5, help="number of repetitions (default: 5)")
    parser.add_argument("--json", type=Path, help="also write the report as JSON")
    args = parser.parse_args()
    if not args.input.is_file():
        print(f"error: input file does not exist: {args.input}", file=sys.stderr)
        return 2
    if args.runs < 1:
        print("error: --runs must be positive", file=sys.stderr)
        return 2
    try:
        report = run_benchmark(args.input, args.runs)
    except Exception as exc:
        print(f"error: benchmark failed: {exc}", file=sys.stderr)
        return 1
    print(_markdown(report))
    if args.json is not None:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
