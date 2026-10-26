"""Emit a fixed application signal for local test Collector verification."""

from __future__ import annotations

from app.config import get_settings
from app.telemetry import create_telemetry


def main() -> int:
    telemetry = create_telemetry(get_settings())
    try:
        if not telemetry.export_enabled:
            raise RuntimeError("Set an OTLP endpoint to export the synthetic test signal")
        telemetry.emit_synthetic_resource_identity_signal()
        if not telemetry.force_flush():
            raise RuntimeError("OpenTelemetry providers did not flush the synthetic test signal")
    finally:
        telemetry.shutdown()

    print("Synthetic application telemetry was flushed to the configured OTLP endpoint.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
