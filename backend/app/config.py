import os
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from the process environment only."""

    model_config = SettingsConfigDict(extra="ignore")

    osa_environment: Literal["development", "production"] = Field(
        "development", validation_alias="OSA_ENVIRONMENT"
    )
    osa_version: str = Field("local", min_length=1, validation_alias="OSA_VERSION")
    osa_trace_sampling_ratio: float = Field(
        1.0,
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
        validation_alias="OSA_TRACE_SAMPLING_RATIO",
    )
    otel_exporter_otlp_endpoint: str | None = Field(
        None, validation_alias="OTEL_EXPORTER_OTLP_ENDPOINT"
    )
    otel_exporter_otlp_protocol: str | None = Field(
        None, validation_alias="OTEL_EXPORTER_OTLP_PROTOCOL"
    )
    otel_exporter_otlp_traces_endpoint: str | None = Field(
        None, validation_alias="OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"
    )
    otel_exporter_otlp_metrics_endpoint: str | None = Field(
        None, validation_alias="OTEL_EXPORTER_OTLP_METRICS_ENDPOINT"
    )
    otel_exporter_otlp_logs_endpoint: str | None = Field(
        None, validation_alias="OTEL_EXPORTER_OTLP_LOGS_ENDPOINT"
    )
    otel_token_file: str | None = Field(None, validation_alias="OSA_OTLP_TOKEN_FILE")
    dataset_dir: Path = Field(Path("./tmp_datasets"), validation_alias="DATASET_DIR")
    dataset_ttl_hours: int = Field(24, gt=0, validation_alias="DATASET_TTL_HOURS")
    # Test-only override: a lifetime in seconds that wins over DATASET_TTL_HOURS, so a browser
    # test can see a real expiry without waiting. Unset in production.
    dataset_ttl_seconds: int | None = Field(None, gt=0, validation_alias="DATASET_TTL_SECONDS")
    max_upload_bytes: int = Field(52_428_800, gt=0, validation_alias="MAX_UPLOAD_BYTES")
    max_rows: int = Field(500_000, gt=0, validation_alias="MAX_ROWS")
    customer_id_max_length: int = Field(128, gt=0, validation_alias="CUSTOMER_ID_MAX_LENGTH")
    cleanup_interval_minutes: int = Field(15, gt=0, validation_alias="CLEANUP_INTERVAL_MINUTES")
    max_datasets: int = Field(200, gt=0, validation_alias="MAX_DATASETS")
    response_cache_max_entries: int = Field(
        256, ge=0, validation_alias="RESPONSE_CACHE_MAX_ENTRIES"
    )
    response_cache_ttl_seconds: int = Field(
        300, gt=0, validation_alias="RESPONSE_CACHE_TTL_SECONDS"
    )
    public_demo_mode: bool = Field(False, validation_alias="PUBLIC_DEMO_MODE")

    @property
    def dataset_ttl(self) -> timedelta:
        if self.dataset_ttl_seconds is not None:
            return timedelta(seconds=self.dataset_ttl_seconds)
        return timedelta(hours=self.dataset_ttl_hours)

    @field_validator("dataset_dir", mode="before")
    @classmethod
    def _dataset_dir_not_blank(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            raise ValueError("must not be empty")
        return value


def configured_osa_environment() -> str | None:
    """Return the raw deployment environment, preserving whether it was explicitly set."""
    return os.environ.get("OSA_ENVIRONMENT")


@lru_cache
def get_settings() -> Settings:
    return Settings()
