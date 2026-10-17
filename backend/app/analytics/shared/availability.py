"""Explicit availability contracts for analytics modules."""

from dataclasses import dataclass
from enum import StrEnum


class AvailabilityState(StrEnum):
    """The five serialized states used when a module cannot show normal data."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    INSUFFICIENT_DATA = "insufficient_data"
    LOW_COVERAGE = "low_coverage"
    ZERO_RESULT = "zero_result"


@dataclass(frozen=True)
class Availability:
    """A state plus the explanation required for every non-available state."""

    state: AvailabilityState
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.state is AvailabilityState.AVAILABLE:
            if self.reason is not None:
                raise ValueError("available state must not have a reason")
        elif not self.reason or not self.reason.strip():
            raise ValueError("non-available states require a nonempty reason")
