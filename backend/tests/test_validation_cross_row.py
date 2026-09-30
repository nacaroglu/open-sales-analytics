from datetime import date
from pathlib import Path

from app.validation import MAX_REPORTED_ERRORS, stage_csv, validate_rows

FIXTURES = Path(__file__).parent / "fixtures" / "cross_row"
TODAY = date(2025, 6, 1)
HEADER = "order_id,order_date,product_id,product_name,quantity,unit_price"


def run(path):
    connection = stage_csv(path)
    try:
        return validate_rows(connection, TODAY)
    finally:
        connection.close()


def run_rows(tmp_path, *rows):
    path = tmp_path / "upload.csv"
    path.write_text(HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return run(path)


def summary(result):
    return [(e.row_number, e.field, e.code) for e in result.errors]


def line(order, product, name="Mug", quantity=1, price="9.99"):
    return f"{order},2025-01-02,{product},{name},{quantity},{price}"


# --- fixtures -----------------------------------------------------------------


def test_clean_multi_line_orders_are_valid():
    result = run(FIXTURES / "clean_multi_line_orders.csv")

    assert result.errors == [] and result.warnings == []


def test_duplicate_line_fixture():
    result = run(FIXTURES / "duplicate_line.csv")

    assert summary(result) == [(4, None, "duplicate_line")]
    assert "row 2" in result.errors[0].reason


def test_conflicting_name_fixture():
    result = run(FIXTURES / "conflicting_name.csv")

    assert summary(result) == [(4, "product_name", "conflicting_product_name")]
    reason = result.errors[0].reason
    assert "'p1'" in reason and "'Mug'" in reason and "'Mugg'" in reason


def test_file_breaking_both_rules_and_a_row_level_rule():
    result = run(FIXTURES / "all_rules_together.csv")

    assert summary(result) == [
        (3, None, "duplicate_line"),
        (4, "product_name", "conflicting_product_name"),
        (4, "quantity", "invalid_quantity"),
    ]
    assert result.error_count == 3


# --- duplicate_line -----------------------------------------------------------


def test_each_repeat_after_the_first_is_its_own_error(tmp_path):
    result = run_rows(tmp_path, line("o1", "p1"), line("o1", "p1"), line("o1", "p1"))

    assert summary(result) == [(3, None, "duplicate_line"), (4, None, "duplicate_line")]
    assert all("row 2" in e.reason for e in result.errors)


def test_duplicates_need_the_same_order_and_the_same_product(tmp_path):
    result = run_rows(
        tmp_path,
        line("o1", "p1"),
        line("o1", "p2", name="Cup"),
        line("o2", "p1"),
    )

    assert result.errors == []


def test_same_product_in_two_orders_at_two_prices_is_valid(tmp_path):
    result = run_rows(tmp_path, line("o1", "p1", price="9.99"), line("o2", "p1", price="7.50"))

    assert result.errors == []


def test_ids_are_compared_as_text(tmp_path):
    result = run_rows(
        tmp_path,
        line("7", "p1"),
        line("07", "p1"),
        line("8", "7", name="A"),
        line("8", "07", name="B"),
    )

    assert result.errors == []


def test_ids_are_trimmed_before_comparing(tmp_path):
    result = run_rows(tmp_path, line("o1", "p1"), line(" o1 ", " p1 "))

    assert summary(result) == [(3, None, "duplicate_line")]


def test_a_duplicate_is_reported_even_when_the_row_has_another_error(tmp_path):
    result = run_rows(tmp_path, line("o1", "p1"), line("o1", "p1", quantity=0))

    assert summary(result) == [
        (3, None, "duplicate_line"),
        (3, "quantity", "invalid_quantity"),
    ]
    assert result.error_count == 2


def test_rows_with_a_blank_order_or_product_id_are_ignored(tmp_path):
    result = run_rows(
        tmp_path,
        line("", "p1"),
        line("", "p1"),
        line("o1", ""),
        line("o1", ""),
    )

    assert {e.code for e in result.errors} == {"missing_value"}
    assert result.error_count == 4


# --- conflicting_product_name -------------------------------------------------


def test_one_error_per_product_on_the_first_differing_row(tmp_path):
    result = run_rows(
        tmp_path,
        line("o1", "p1", name="Mug"),
        line("o2", "p1", name="Mug"),
        line("o3", "p1", name="Cup"),
        line("o4", "p1", name="Cup"),
        line("o5", "p1", name="Mug"),
    )

    assert summary(result) == [(4, "product_name", "conflicting_product_name")]


def test_three_names_give_one_error_that_says_how_many(tmp_path):
    result = run_rows(
        tmp_path,
        line("o1", "p1", name="A"),
        line("o2", "p1", name="B"),
        line("o3", "p1", name="C"),
    )

    assert summary(result) == [(3, "product_name", "conflicting_product_name")]
    reason = result.errors[0].reason
    assert "3 different names" in reason and "'A'" in reason and "'B'" in reason
    assert "'C'" not in reason


def test_two_products_with_conflicts_give_two_errors(tmp_path):
    result = run_rows(
        tmp_path,
        line("o1", "p1", name="A"),
        line("o2", "p2", name="X"),
        line("o3", "p1", name="B"),
        line("o4", "p2", name="Y"),
    )

    assert summary(result) == [
        (4, "product_name", "conflicting_product_name"),
        (5, "product_name", "conflicting_product_name"),
    ]


def test_names_are_trimmed_but_case_sensitive(tmp_path):
    trimmed = run_rows(tmp_path, line("o1", "p1", name="Mug"), line("o2", "p1", name=" Mug "))
    cased = run_rows(tmp_path, line("o1", "p1", name="Mug"), line("o2", "p1", name="mug"))

    assert trimmed.errors == []
    assert summary(cased) == [(3, "product_name", "conflicting_product_name")]


def test_different_products_may_share_a_name(tmp_path):
    result = run_rows(tmp_path, line("o1", "p1", name="Mug"), line("o2", "p2", name="Mug"))

    assert result.errors == []


def test_rows_with_a_blank_name_or_product_id_are_ignored(tmp_path):
    result = run_rows(
        tmp_path,
        line("o1", "p1", name="Mug"),
        line("o2", "p1", name=""),
        line("o3", "", name="A"),
        line("o4", "", name="B"),
    )

    assert {e.code for e in result.errors} == {"missing_value"}
    assert result.error_count == 3


# --- merging ------------------------------------------------------------------


def test_errors_merge_with_row_level_errors_in_row_order(tmp_path):
    result = run_rows(
        tmp_path,
        line("o1", "p1"),
        line("o2", "p2", name="Cup", quantity=0),
        line("o1", "p1"),
        line("o3", "p1", name="Other"),
    )

    assert [(e.row_number, e.code) for e in result.errors] == [
        (3, "invalid_quantity"),
        (4, "duplicate_line"),
        (5, "conflicting_product_name"),
    ]


def test_combined_total_is_counted_and_the_list_is_capped(tmp_path):
    duplicates = [line("o1", "p1")] * 60
    bad_quantities = [line(f"q{n}", f"q{n}", name="N", quantity=0) for n in range(60)]

    result = run_rows(tmp_path, *duplicates, *bad_quantities)

    assert result.error_count == 59 + 60
    assert len(result.errors) == MAX_REPORTED_ERRORS
    rows = [e.row_number for e in result.errors]
    assert rows == sorted(rows)


def test_cross_row_errors_are_never_counted_twice(tmp_path):
    result = run_rows(tmp_path, line("o1", "p1"), line("o1", "p1", name="Other"))

    assert result.error_count == len(result.errors) == 2
