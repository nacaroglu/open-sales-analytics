import shutil
from datetime import date
from pathlib import Path

import pytest

from app.validation import stage_csv, validate_rows, validate_structure

FIXTURES = Path(__file__).parent / "fixtures" / "rows"
TODAY = date(2025, 6, 1)
HEADER = "order_id,order_date,product_id,product_name,quantity,unit_price"
GOOD = "o1,2025-01-02,p1,Mug,1,9.99"


def run(path, today=TODAY):
    connection = stage_csv(path)
    try:
        return validate_rows(connection, today)
    finally:
        connection.close()


def run_text(tmp_path, text, today=TODAY):
    path = tmp_path / "upload.csv"
    path.write_text(text, encoding="utf-8", newline="")
    return run(path, today)


def one_row(tmp_path, **values):
    row = {
        "order_id": "o1", "order_date": "2025-01-02", "product_id": "p1",
        "product_name": "Mug", "quantity": "1", "unit_price": "9.99",
    } | values
    return run_text(tmp_path, HEADER + "\n" + ",".join(row.values()) + "\n")


def summary(result):
    return [(e.row_number, e.field, e.code) for e in result.errors]


# --- one fixture file per rule ------------------------------------------------


def test_clean_fixture_has_no_errors_and_no_warnings():
    result = run(FIXTURES / "clean.csv")

    assert result.errors == [] and result.error_count == 0 and result.warnings == []


@pytest.mark.parametrize(
    ("fixture", "field", "code"),
    [
        ("missing_value", "order_date", "missing_value"),
        ("invalid_date", "order_date", "invalid_date"),
        ("future_date", "order_date", "future_date"),
        ("invalid_quantity", "quantity", "invalid_quantity"),
        ("invalid_price", "unit_price", "invalid_price"),
        ("negative_price", "unit_price", "negative_price"),
        ("malformed_row", None, "malformed_row"),
    ],
)
def test_each_fixture_has_exactly_the_one_expected_error(fixture, field, code):
    result = run(FIXTURES / f"{fixture}.csv")

    assert summary(result) == [(3, field, code)]
    assert result.error_count == 1
    assert result.errors[0].reason


def test_zero_price_fixture_is_a_warning_not_an_error():
    result = run(FIXTURES / "zero_price.csv")

    assert result.errors == []
    (warning,) = result.warnings
    assert (warning.code, warning.field, warning.row_number) == ("zero_price", "unit_price", None)
    assert "1 line has" in warning.reason


# --- staging ------------------------------------------------------------------


def test_staging_is_all_varchar_and_keeps_leading_zeros(tmp_path):
    path = tmp_path / "u.csv"
    path.write_text(f"{HEADER}\n007,2025-01-02,0042,Mug,1,9.99\n")

    connection = stage_csv(path)

    types = dict(
        connection.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'staging'"
        ).fetchall()
    )
    assert {name: kind for name, kind in types.items() if name != "row_number"} == {
        c: "VARCHAR" for c in
        ("order_id", "order_date", "product_id", "product_name", "quantity", "unit_price")
    }
    assert connection.execute("SELECT order_id, product_id FROM staging").fetchone() == ("007", "0042")


def test_row_numbers_start_at_two_for_the_first_data_row(tmp_path):
    path = tmp_path / "u.csv"
    path.write_text(f"{HEADER}\n{GOOD}\n{GOOD}\n")

    connection = stage_csv(path)

    assert connection.execute("SELECT row_number FROM staging ORDER BY 1").fetchall() == [(2,), (3,)]


def test_quoted_comma_and_line_break_are_one_value_and_one_record(tmp_path):
    text = (
        f'{HEADER}\no1,2025-01-02,p1,"Mug, big",1,9.99\n'
        'o2,2025-01-02,p2,"Two\nlines",1,9.99\no3,2025-01-02,p3,Mug,1,9.99\n'
    )
    path = tmp_path / "u.csv"
    path.write_text(text)

    connection = stage_csv(path)

    assert connection.execute("SELECT row_number, product_name FROM staging ORDER BY 1").fetchall() == [
        (2, "Mug, big"), (3, "Two\nlines"), (4, "Mug"),
    ]
    assert validate_rows(connection, TODAY).errors == []


def test_blank_lines_take_a_row_number_but_are_not_rows(tmp_path):
    path = tmp_path / "u.csv"
    path.write_text(f"{HEADER}\n\n{GOOD}\n")

    connection = stage_csv(path)

    assert connection.execute("SELECT row_number FROM staging").fetchall() == [(3,)]


def test_extra_columns_are_never_read_or_checked(tmp_path):
    result = run_text(
        tmp_path,
        f"{HEADER},notes\n{GOOD},SECRET-NOTE\no2,2025-01-02,p2,Cup,1,4.50,\n",
    )

    assert result.errors == []
    assert "SECRET-NOTE" not in str(result)


def test_temporary_files_are_removed(tmp_path):
    path = tmp_path / "u.csv"
    path.write_text(f"{HEADER}\n{GOOD}\n")

    stage_csv(path).close()

    assert [p.name for p in tmp_path.iterdir()] == ["u.csv"]


def test_temporary_files_are_removed_when_staging_fails(tmp_path):
    path = tmp_path / "u.csv"
    path.write_text("order_id,order_date\no1,2025-01-02\n")

    with pytest.raises(ValueError):
        stage_csv(path)

    assert [p.name for p in tmp_path.iterdir()] == ["u.csv"]


def test_row_numbers_stay_correct_with_a_file_that_passed_structure_check(tmp_path):
    path = tmp_path / "u.csv"
    path.write_bytes(b"\xef\xbb\xbf" + f"{HEADER}\n{GOOD}\n".encode())
    assert validate_structure(path, 10**9, 10**9).ok

    connection = stage_csv(path)

    assert connection.execute("SELECT row_number FROM staging").fetchall() == [(2,)]


# --- whitespace and missing values -------------------------------------------


def test_values_are_trimmed_before_checking(tmp_path):
    result = run_text(tmp_path, f"{HEADER}\n o1 , 2025-01-02 ,p1, Mug , 1 , 9.99 \n")

    assert result.errors == []


@pytest.mark.parametrize("field", ["order_id", "order_date", "product_id", "product_name", "quantity", "unit_price"])
@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_value_is_missing_and_only_reported_once(tmp_path, field, blank):
    result = one_row(tmp_path, **{field: blank})

    assert summary(result) == [(2, field, "missing_value")]


# --- dates --------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["2025-1-5", "05/01/2025", "2025-01-05T10:00", "20250105", "2025-02-30", "2025-13-01", "abc", "2025-01-5"],
)
def test_bad_dates(tmp_path, value):
    assert summary(one_row(tmp_path, order_date=value)) == [(2, "order_date", "invalid_date")]


def test_today_is_accepted_and_tomorrow_is_the_future(tmp_path):
    today = date(2025, 6, 1)

    assert one_row(tmp_path, order_date="2025-06-01").errors == []
    tomorrow = run_text(tmp_path, f"{HEADER}\no1,2025-06-02,p1,Mug,1,9.99\n", today=today)
    assert summary(tomorrow) == [(2, "order_date", "future_date")]


def test_today_defaults_to_the_current_utc_date(tmp_path):
    result = run_text(tmp_path, f"{HEADER}\no1,2999-12-31,p1,Mug,1,9.99\n", today=None)

    assert summary(result) == [(2, "order_date", "future_date")]


# --- quantity -----------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["1.5", "1.0", "abc", "1e3", "1,000", "0", "-3", "+3", "2147483648", "99999999999999999999"],
)
def test_bad_quantities(tmp_path, value):
    text = f'{HEADER}\no1,2025-01-02,p1,Mug,"{value}",9.99\n'

    assert summary(run_text(tmp_path, text)) == [(2, "quantity", "invalid_quantity")]


@pytest.mark.parametrize("value", ["1", "2147483647", "007"])
def test_good_quantities(tmp_path, value):
    assert one_row(tmp_path, quantity=value).errors == []


# --- price --------------------------------------------------------------------


@pytest.mark.parametrize(
    "value",
    ["abc", "$5", "1e3", "1.23456", "123456789012345", ".5", "5.", "+5", "1.2.3"],
)
def test_bad_prices(tmp_path, value):
    text = f'{HEADER}\no1,2025-01-02,p1,Mug,1,"{value}"\n'

    assert summary(run_text(tmp_path, text)) == [(2, "unit_price", "invalid_price")]


def test_price_with_comma_decimal_is_invalid(tmp_path):
    text = f'{HEADER}\no1,2025-01-02,p1,Mug,1,"1,50"\n'

    assert summary(run_text(tmp_path, text)) == [(2, "unit_price", "invalid_price")]


@pytest.mark.parametrize("value", ["9", "9.9", "9.9999", "12345678901234", "12345678901234.9999"])
def test_good_prices(tmp_path, value):
    assert one_row(tmp_path, unit_price=value).errors == []


@pytest.mark.parametrize("value", ["-0.01", "-5", "-9.9999"])
def test_negative_prices(tmp_path, value):
    assert summary(one_row(tmp_path, unit_price=value)) == [(2, "unit_price", "negative_price")]


def test_too_precise_negative_price_is_invalid_not_negative(tmp_path):
    assert summary(one_row(tmp_path, unit_price="-1.23456")) == [(2, "unit_price", "invalid_price")]


@pytest.mark.parametrize("value", ["0", "0.0", "0.0000"])
def test_zero_price_is_accepted_with_a_warning(tmp_path, value):
    result = one_row(tmp_path, unit_price=value)

    assert result.errors == []
    assert [w.code for w in result.warnings] == ["zero_price"]


def test_zero_price_gives_one_warning_stating_how_many_lines(tmp_path):
    lines = "\n".join(f"o{n},2025-01-02,p1,Mug,1,0" for n in range(3))
    result = run_text(tmp_path, f"{HEADER}\n{lines}\n{GOOD}\n")

    assert len(result.warnings) == 1
    assert "3 lines have" in result.warnings[0].reason


# --- malformed rows -----------------------------------------------------------


@pytest.mark.parametrize("row", ["o1,2025-01-02,p1,Mug,1", "o1,2025-01-02,p1,Mug,1,9.99,extra"])
def test_wrong_number_of_fields(tmp_path, row):
    result = run_text(tmp_path, f"{HEADER}\n{row}\n{GOOD}\n")

    assert summary(result) == [(2, None, "malformed_row")]
    assert "header has 6" in result.errors[0].reason


# --- counts, ordering, caps ---------------------------------------------------


def test_a_row_with_three_bad_fields_gives_three_errors_in_column_order(tmp_path):
    result = run_text(tmp_path, f"{HEADER}\n,2025-1-5,p1,Mug,1,9.99\no1,2025-01-02,p1,Mug,0,-1\n")

    assert summary(result) == [
        (2, "order_id", "missing_value"),
        (2, "order_date", "invalid_date"),
        (3, "quantity", "invalid_quantity"),
        (3, "unit_price", "negative_price"),
    ]


def test_errors_are_ordered_by_row_then_column_with_malformed_in_place(tmp_path):
    text = f"{HEADER}\no1,2025-01-02,p1,Mug,0,9.99\nshort\no3,2025-01-02,p1,Mug,0,9.99\n"

    result = run_text(tmp_path, text)

    assert [(e.row_number, e.code) for e in result.errors] == [
        (2, "invalid_quantity"), (3, "malformed_row"), (4, "invalid_quantity"),
    ]


def test_250_bad_rows_give_100_errors_and_a_true_count(tmp_path):
    lines = "\n".join(f"o{n},2025-01-02,p1,Mug,0,9.99" for n in range(250))

    result = run_text(tmp_path, f"{HEADER}\n{lines}\n")

    assert len(result.errors) == 100
    assert result.error_count == 250
    assert result.errors[0].row_number == 2 and result.errors[-1].row_number == 101


def test_long_values_are_shortened_in_reasons(tmp_path):
    result = one_row(tmp_path, quantity="x" * 5000)

    assert len(result.errors[0].reason) < 300
