from datetime import datetime, timedelta, timezone

import pytest
from app.release_version import generate_version


def test_version_uses_utc_timestamp_and_source_sha_prefix() -> None:
    local_time = datetime(2026, 10, 27, 16, 30, 45, tzinfo=timezone(timedelta(hours=3)))

    assert generate_version("ABCDEF0123456789abcdef0123456789abcdef01", local_time) == (
        "20261027-133045-abcdef0"
    )


@pytest.mark.parametrize("source_sha", ["", "abc1234", "g" * 40, "a" * 39, "a" * 65])
def test_version_rejects_malformed_source_sha(source_sha: str) -> None:
    with pytest.raises(ValueError, match="source commit SHA"):
        generate_version(source_sha, datetime(2026, 10, 27, tzinfo=timezone.utc))


def test_version_rejects_naive_generation_time() -> None:
    with pytest.raises(ValueError, match="timezone"):
        generate_version("a" * 40, datetime(2026, 10, 27))
