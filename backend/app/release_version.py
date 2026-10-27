#!/usr/bin/env python3
"""Generate the human-readable version for an immutable OSA image build."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone

_GIT_OBJECT_ID = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")


def generate_version(source_sha: str, now: datetime | None = None) -> str:
    """Return a UTC timestamp and the first seven lowercase SHA characters."""
    if not _GIT_OBJECT_ID.fullmatch(source_sha):
        raise ValueError("source commit SHA must be a 40- or 64-character hexadecimal object ID")

    current_time = datetime.now(timezone.utc) if now is None else now
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise ValueError("generation time must include a timezone")
    timestamp = current_time.astimezone(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{source_sha[:7].lower()}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_sha", help="full Git commit SHA to identify this build")
    args = parser.parse_args()
    try:
        print(generate_version(args.source_sha))
    except (ValueError, OverflowError) as exc:
        print(f"release version generation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
