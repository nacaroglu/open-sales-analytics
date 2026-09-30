import csv
import os
from collections import Counter

from app.validation.result import Issue, ValidationResult

REQUIRED_COLUMNS = (
    "order_id",
    "order_date",
    "product_id",
    "product_name",
    "quantity",
    "unit_price",
)


def _megabytes(byte_count: int) -> str:
    return f"{byte_count / (1024 * 1024):.3g} MB"


def validate_structure(
    path: str | os.PathLike[str], max_upload_bytes: int, max_rows: int
) -> ValidationResult:
    """Check file-level rules: size, encoding, row count and header.

    Reasons only ever mention column names and limits, never cell values.
    """
    result = ValidationResult()

    size = os.path.getsize(path)
    if size > max_upload_bytes:
        result.add_error(
            Issue(
                code="file_too_large",
                reason=f"The file is larger than the {_megabytes(max_upload_bytes)} limit.",
            )
        )
        return result
    if size == 0:
        result.add_error(Issue(code="empty_file", reason="The file is empty."))
        return result

    header: list[str] | None = None
    data_rows = 0
    try:
        # utf-8-sig drops a leading BOM so the first header is still recognised.
        with open(path, encoding="utf-8-sig", newline="") as handle:
            for record in csv.reader(handle):
                if not record:  # blank line
                    continue
                if header is None:
                    header = [name.strip() for name in record]
                    continue
                data_rows += 1
                if data_rows > max_rows:
                    break
    except UnicodeDecodeError:
        result.add_error(Issue(code="invalid_encoding", reason="The file is not valid UTF-8 text."))
        return result
    except csv.Error:
        result.add_error(Issue(code="malformed_csv", reason="The file could not be read as CSV."))
        return result

    if header is None:
        result.add_error(Issue(code="empty_file", reason="The file is empty."))
        return result

    _check_header(header, result)

    if data_rows > max_rows:
        result.add_error(
            Issue(
                code="too_many_rows",
                reason=f"The file has more than the {max_rows:,} data rows allowed.",
            )
        )
    elif data_rows == 0:
        result.add_error(
            Issue(code="no_data_rows", reason="The file has a header row but no data rows.")
        )
    return result


def _check_header(header: list[str], result: ValidationResult) -> None:
    counts = Counter(header)
    for column in REQUIRED_COLUMNS:
        if counts[column] == 0:
            result.add_error(
                Issue(
                    code="missing_column",
                    field=column,
                    reason=f"The required column '{column}' is missing.",
                )
            )
        elif counts[column] > 1:
            result.add_error(
                Issue(
                    code="duplicate_column",
                    field=column,
                    reason=f"The column '{column}' appears {counts[column]} times.",
                )
            )
    for name in header:
        if name not in REQUIRED_COLUMNS:
            result.add_warning(
                Issue(
                    code="extra_column",
                    field=name,
                    reason=f"The column '{name}' is not used and will be ignored.",
                )
            )
