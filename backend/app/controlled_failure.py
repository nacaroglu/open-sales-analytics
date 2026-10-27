"""Run three isolated, development-only dataset creation failure attempts."""

from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from app.config import Settings, get_settings
from app.custom_metrics import use_custom_metrics
from app.domain_telemetry import use_tracer_provider
from app.ingest import CreatedDataset, ingest_csv
from app.telemetry import TelemetryProviders, create_telemetry

_ATTEMPTS = 3


def _arguments(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--confirm-controlled-failure",
        action="store_true",
        help="confirm this development-only command may create expected failures",
    )
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    settings_factory: Callable[[], Settings] = get_settings,
    telemetry_factory: Callable[[Settings], TelemetryProviders] = create_telemetry,
    service: Callable[..., Any] = ingest_csv,
    temp_directory_factory: Callable[..., Any] = tempfile.TemporaryDirectory,
) -> int:
    """Run the controlled failure check with injectable boundaries for offline tests."""
    environment = os.environ if environ is None else environ
    if environment.get("OSA_ENVIRONMENT") != "development":
        print("Controlled failure check requires OSA_ENVIRONMENT=development.")
        return 2
    if not _arguments(argv).confirm_controlled_failure:
        print("Pass --confirm-controlled-failure to run this check.")
        return 2

    temporary = None
    telemetry = None
    interrupted = False
    expected_failures = 0
    unexpected = False
    cleanup_ok = True
    try:
        temporary = temp_directory_factory(prefix="osa-controlled-failure-")
        root = Path(temporary.name)
        blocked_storage = root / "blocked-storage"
        blocked_storage.write_text("isolated failure fixture", encoding="utf-8")
        settings = settings_factory().model_copy(update={"dataset_dir": blocked_storage})
        telemetry = telemetry_factory(settings)
        metrics = telemetry.custom_metrics
        if metrics is None:
            print("Controlled failure check could not initialize telemetry.")
            return 1

        try:
            with use_custom_metrics(metrics), use_tracer_provider(telemetry.tracer_provider):
                for attempt in range(_ATTEMPTS):
                    csv_path = root / f"attempt-{attempt + 1}.csv"
                    with csv_path.open("w", encoding="utf-8", newline="") as stream:
                        writer = csv.writer(stream)
                        writer.writerow(
                            (
                                "order_id",
                                "order_date",
                                "product_id",
                                "product_name",
                                "quantity",
                                "unit_price",
                            )
                        )
                        writer.writerow(
                            ("controlled", "2025-01-01", "controlled", "Controlled", 1, 1)
                        )
                    try:
                        result = service(csv_path, "USD", settings, source="upload")
                    except KeyboardInterrupt:
                        interrupted = True
                        break
                    except BaseException as exc:
                        metrics.record_dataset_operation(
                            "create", "upload", "failure", failure_class="internal"
                        )
                        if isinstance(exc, NotADirectoryError):
                            expected_failures += 1
                        else:
                            unexpected = True
                        continue
                    if isinstance(result, CreatedDataset):
                        unexpected = True
                    else:
                        # A validation result is not the intended internal creation failure.
                        unexpected = True
        except KeyboardInterrupt:
            interrupted = True
    except BaseException:
        unexpected = True
    finally:
        if telemetry is not None:
            try:
                if not telemetry.force_flush():
                    unexpected = True
                telemetry.shutdown()
            except BaseException:
                unexpected = True
        if temporary is not None:
            try:
                temporary.cleanup()
                cleanup_ok = not Path(temporary.name).exists()
            except BaseException:
                cleanup_ok = False
            if not cleanup_ok:
                try:
                    shutil.rmtree(temporary.name)
                except OSError:
                    pass

    if interrupted:
        print("Controlled failure check interrupted; temporary storage cleanup attempted.")
        return 130 if cleanup_ok else 1
    if not cleanup_ok:
        print("Controlled failure check failed: temporary storage cleanup failed.")
        return 1
    if unexpected or expected_failures != _ATTEMPTS:
        print("Controlled failure check failed; see bounded application telemetry for results.")
        return 1
    print(
        "Controlled failure check passed: 3 internal dataset-creation failures; temporary storage cleaned."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
