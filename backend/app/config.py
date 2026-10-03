from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, read from the process environment only."""

    model_config = SettingsConfigDict(extra="ignore")

    dataset_dir: Path = Field(Path("./tmp_datasets"), validation_alias="DATASET_DIR")
    dataset_ttl_hours: int = Field(24, gt=0, validation_alias="DATASET_TTL_HOURS")
    # Test-only override: a lifetime in seconds that wins over DATASET_TTL_HOURS, so a browser
    # test can see a real expiry without waiting. Unset in production.
    dataset_ttl_seconds: int | None = Field(None, gt=0, validation_alias="DATASET_TTL_SECONDS")
    max_upload_bytes: int = Field(52_428_800, gt=0, validation_alias="MAX_UPLOAD_BYTES")
    max_rows: int = Field(500_000, gt=0, validation_alias="MAX_ROWS")
    cleanup_interval_minutes: int = Field(15, gt=0, validation_alias="CLEANUP_INTERVAL_MINUTES")
    max_datasets: int = Field(200, gt=0, validation_alias="MAX_DATASETS")
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


@lru_cache
def get_settings() -> Settings:
    return Settings()
