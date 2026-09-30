import tracemalloc

import pytest
from app.validation import MAX_REPORTED_ERRORS, Issue, ValidationResult, validate_structure

HEADER = "order_id,order_date,product_id,product_name,quantity,unit_price"
ROW = "o1,2025-01-02,p1,Mug,1,9.99"
BIG = 10**9


def check(tmp_path, content, max_upload_bytes=BIG, max_rows=BIG):
    path = tmp_path / "upload.csv"
    path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    return validate_structure(path, max_upload_bytes, max_rows)


def codes(issues):
    return [i.code for i in issues]


def test_clean_file_passes(tmp_path):
    result = check(tmp_path, f"{HEADER}\n{ROW}\n")

    assert result.errors == []
    assert result.error_count == 0
    assert result.warnings == []
    assert result.ok


def test_issue_has_the_four_fields(tmp_path):
    result = check(tmp_path, f"{HEADER},extra\n{ROW},x\n")

    (warning,) = result.warnings
    assert (warning.row_number, warning.field, warning.code) == (None, "extra", "extra_column")
    assert isinstance(warning.reason, str) and warning.reason


def test_result_serialises_to_plain_dicts(tmp_path):
    data = check(tmp_path, f"{HEADER},extra\n{ROW},x\n").to_dict()

    assert set(data) == {"errors", "error_count", "warnings"}
    assert set(data["warnings"][0]) == {"code", "reason", "row_number", "field"}


def test_errors_are_capped_but_total_is_true():
    result = ValidationResult()
    for n in range(250):
        result.add_error(Issue(code="x", reason="r", row_number=n))

    assert len(result.errors) == MAX_REPORTED_ERRORS == 100
    assert result.error_count == 250
    assert result.errors[0].row_number == 0


def test_size_at_the_limit_passes_and_one_byte_more_fails(tmp_path):
    content = f"{HEADER}\n{ROW}\n".encode()

    assert check(tmp_path, content, max_upload_bytes=len(content)).ok

    result = check(tmp_path, content, max_upload_bytes=len(content) - 1)
    assert codes(result.errors) == ["file_too_large"]
    assert result.error_count == 1


def test_file_too_large_states_the_limit_in_mb(tmp_path):
    limit = 50 * 1024 * 1024
    content = b"x" * (limit + 1)

    result = check(tmp_path, content, max_upload_bytes=limit)

    assert codes(result.errors) == ["file_too_large"]
    assert "50 MB" in result.errors[0].reason


def test_rows_at_the_limit_pass_and_one_more_fails(tmp_path):
    rows = "\n".join([ROW] * 3)

    assert check(tmp_path, f"{HEADER}\n{rows}\n", max_rows=3).ok

    result = check(tmp_path, f"{HEADER}\n{rows}\n{ROW}\n", max_rows=3)
    assert codes(result.errors) == ["too_many_rows"]
    assert "3" in result.errors[0].reason


def test_header_and_trailing_newline_are_not_rows(tmp_path):
    with_newline = check(tmp_path, f"{HEADER}\n{ROW}\n", max_rows=1)
    without_newline = check(tmp_path, f"{HEADER}\n{ROW}", max_rows=1)
    blank_lines_at_end = check(tmp_path, f"{HEADER}\n{ROW}\n\n\n", max_rows=1)

    assert with_newline.ok and without_newline.ok and blank_lines_at_end.ok


def test_quoted_line_break_counts_as_one_row(tmp_path):
    content = f'{HEADER}\no1,2025-01-02,p1,"Big\nMug",1,9.99\n'

    assert check(tmp_path, content, max_rows=1).ok


def test_row_counting_streams_the_file(tmp_path):
    rows = "\n".join([ROW] * 200_000)
    path = tmp_path / "big.csv"
    path.write_text(f"{HEADER}\n{rows}\n")
    assert path.stat().st_size > 5_000_000

    tracemalloc.start()
    result = validate_structure(path, BIG, 200_000)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert result.ok
    assert peak < 1_000_000


def test_invalid_utf8_is_rejected(tmp_path):
    result = check(tmp_path, HEADER.encode() + b"\no1,2025-01-02,p1,Caf\xe9,1,9.99\n")

    assert codes(result.errors) == ["invalid_encoding"]


def test_bom_is_accepted_and_first_header_recognised(tmp_path):
    result = check(tmp_path, b"\xef\xbb\xbf" + f"{HEADER}\n{ROW}\n".encode())

    assert result.errors == []
    assert result.warnings == []


def test_zero_byte_file(tmp_path):
    assert codes(check(tmp_path, b"").errors) == ["empty_file"]


def test_only_blank_lines_is_empty(tmp_path):
    assert codes(check(tmp_path, "\n\n").errors) == ["empty_file"]


def test_header_only_file_has_no_data_rows(tmp_path):
    assert codes(check(tmp_path, f"{HEADER}\n").errors) == ["no_data_rows"]


def test_each_missing_header_is_one_error(tmp_path):
    result = check(tmp_path, "order_id,order_date,product_id\no1,2025-01-02,p1\n")

    assert codes(result.errors) == ["missing_column"] * 3
    assert [e.field for e in result.errors] == ["product_name", "quantity", "unit_price"]
    assert result.error_count == 3


def test_header_names_are_trimmed(tmp_path):
    header = " order_id , order_date,product_id ,product_name,quantity,unit_price"

    result = check(tmp_path, f"{header}\n{ROW}\n")

    assert result.ok and result.warnings == []


def test_header_names_are_case_sensitive(tmp_path):
    header = "Order_ID,order_date,product_id,product_name,quantity,unit_price"

    result = check(tmp_path, f"{header}\n{ROW}\n")

    assert [(e.code, e.field) for e in result.errors] == [("missing_column", "order_id")]
    assert [(w.code, w.field) for w in result.warnings] == [("extra_column", "Order_ID")]


def test_duplicated_required_header(tmp_path):
    result = check(tmp_path, f"{HEADER},quantity\n{ROW},2\n")

    assert [(e.code, e.field) for e in result.errors] == [("duplicate_column", "quantity")]


def test_each_extra_column_is_one_warning_and_not_an_error(tmp_path):
    result = check(tmp_path, f"{HEADER},notes,region\n{ROW},a,b\n")

    assert result.ok
    assert [(w.code, w.field) for w in result.warnings] == [
        ("extra_column", "notes"),
        ("extra_column", "region"),
    ]


def test_columns_in_any_order_are_accepted(tmp_path):
    header = "unit_price,quantity,product_name,product_id,order_date,order_id"

    result = check(tmp_path, f"{header}\n9.99,1,Mug,p1,2025-01-02,o1\n")

    assert result.ok and result.warnings == []


def test_unreadable_csv_is_reported_not_raised(tmp_path):
    huge_field = "x" * 200_000

    result = check(tmp_path, f"{HEADER}\no1,2025-01-02,p1,{huge_field},1,9.99\n")

    assert codes(result.errors) == ["malformed_csv"]


@pytest.mark.parametrize(
    "content",
    [
        f"{HEADER}\no1,2025-01-02,p1,SECRET-NAME,-3,9.99\n",
        f"{HEADER}\n\xa0SECRET-VALUE,x\n",
    ],
)
def test_reasons_never_quote_cell_values(tmp_path, content):
    result = check(tmp_path, content, max_rows=0)

    everything = " ".join(i.reason for i in result.errors + result.warnings)
    assert "SECRET" not in everything
