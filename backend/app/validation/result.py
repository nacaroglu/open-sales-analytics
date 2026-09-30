from dataclasses import asdict, dataclass, field

MAX_REPORTED_ERRORS = 100


@dataclass(frozen=True)
class Issue:
    """One validation error or warning.

    row_number is the record's position in the file with the header as row 1,
    or None for a problem with the file as a whole. field is the column name,
    or None when no single column is at fault.
    """

    code: str
    reason: str
    row_number: int | None = None
    field: str | None = None


@dataclass
class ValidationResult:
    errors: list[Issue] = field(default_factory=list)
    error_count: int = 0
    warnings: list[Issue] = field(default_factory=list)

    def add_error(self, issue: Issue) -> None:
        """Count every error but keep only the first MAX_REPORTED_ERRORS."""
        self.error_count += 1
        if len(self.errors) < MAX_REPORTED_ERRORS:
            self.errors.append(issue)

    def add_warning(self, issue: Issue) -> None:
        self.warnings.append(issue)

    @property
    def ok(self) -> bool:
        return self.error_count == 0

    def to_dict(self) -> dict:
        return {
            "errors": [asdict(e) for e in self.errors],
            "error_count": self.error_count,
            "warnings": [asdict(w) for w in self.warnings],
        }
