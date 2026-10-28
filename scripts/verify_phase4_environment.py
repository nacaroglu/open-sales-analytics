#!/usr/bin/env python3
"""Verify a GitHub environment API response has required reviewers."""

from __future__ import annotations

import json
import sys
from typing import Any


def validate_environment_protection(environment: dict[str, Any]) -> None:
    rules = environment.get("protection_rules")
    if not isinstance(rules, list):
        raise ValueError("environment protection rules are missing")
    for rule in rules:
        if not isinstance(rule, dict) or rule.get("type") != "required_reviewers":
            continue
        reviewers = rule.get("reviewers")
        if isinstance(reviewers, list) and reviewers:
            return
    raise ValueError("osa-teardown has no required reviewers")


def main() -> int:
    try:
        environment = json.load(sys.stdin)
        if not isinstance(environment, dict):
            raise ValueError("environment response is not an object")
        validate_environment_protection(environment)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"Environment protection check failed: {exc}", file=sys.stderr)
        return 1
    print("osa-teardown has required reviewers configured.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
