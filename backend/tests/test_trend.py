import inspect
from datetime import date, timedelta
from decimal import Decimal

import duckdb
import pytest
from app.analytics import trend
from app.analytics.kpis import read_kpis
from app.analytics.trend import read_trend
from app.schema import create_dataset, open_dataset_readonly


def build(path, rows):
    create_dataset(path)
    connection = duckdb.connect(str(path))
    try:
        if rows:
            connection.executemany("INSERT INTO line_items VALUES (?, ?, ?, ?, ?, ?)", rows)
    finally:
        connection.close()
    return open_dataset_readonly(path)


def trend_for(tmp_path, rows, start, end):
    connection = build(tmp_path / "trend.duckdb", rows)
    try:
        return read_trend(connection, start, end)
    finally:
        connection.close()


def row(order_id, day, quantity=1, price="1.00"):
    return (order_id, day, "P1", "Bolt", quantity, price)


def span(start, days):
    return start, start + timedelta(days=days - 1)


def test_one_day_range_is_one_daily_bucket(tmp_path):
    day = date(2025, 1, 1)
    result = trend_for(tmp_path, [row("A", day, 2, "1.25")], day, day)
    assert result["granularity"] == "daily"
    assert result["buckets"] == [{"bucket_start": day, "gross_sales": Decimal("2.5")}]


@pytest.mark.parametrize(
    "days, expected",
    [(1, "daily"), (90, "daily"), (91, "weekly"), (730, "weekly"), (731, "monthly")],
)
def test_granularity_thresholds(tmp_path, days, expected):
    start, end = span(date(2025, 1, 1), days)
    assert trend_for(tmp_path, [], start, end)["granularity"] == expected


def test_two_calendar_years_with_leap_day_is_monthly(tmp_path):
    result = trend_for(tmp_path, [], date(2024, 1, 1), date(2025, 12, 31))
    assert result["granularity"] == "monthly"
    assert len(result["buckets"]) == 24


def test_granularity_ignores_data(tmp_path):
    start, end = span(date(2025, 1, 1), 91)
    empty = trend_for(tmp_path, [], start, end)
    full = trend_for(tmp_path, [row("A", start)], start, end)
    assert empty["granularity"] == full["granularity"] == "weekly"


def test_daily_90_days_gives_90_buckets(tmp_path):
    start, end = span(date(2025, 1, 1), 90)
    buckets = trend_for(tmp_path, [], start, end)["buckets"]
    assert len(buckets) == 90
    assert buckets[0]["bucket_start"] == start
    assert buckets[-1]["bucket_start"] == end


def test_gap_in_the_middle_is_zero(tmp_path):
    rows = [row("A", date(2025, 3, 1), 1, "5.00"), row("B", date(2025, 3, 5), 2, "3.00")]
    buckets = trend_for(tmp_path, rows, date(2025, 3, 1), date(2025, 3, 5))["buckets"]
    assert [b["gross_sales"] for b in buckets] == [
        Decimal("5"),
        Decimal("0"),
        Decimal("0"),
        Decimal("0"),
        Decimal("6"),
    ]
    assert [b["bucket_start"] for b in buckets] == [date(2025, 3, d) for d in range(1, 6)]


def test_no_sales_returns_all_buckets_with_zero(tmp_path):
    start, end = span(date(2025, 1, 1), 5)
    buckets = trend_for(tmp_path, [], start, end)["buckets"]
    assert len(buckets) == 5
    assert all(b["gross_sales"] == 0 and type(b["gross_sales"]) is Decimal for b in buckets)


def test_weekly_partial_first_and_last_week(tmp_path):
    # 2025-01-01 is a Wednesday; range 2025-01-01 .. 2025-04-01 (91 days) is weekly.
    start, end = date(2025, 1, 1), date(2025, 4, 1)
    rows = [
        row("out1", date(2024, 12, 30), 100),  # Monday before range: excluded
        row("out2", date(2024, 12, 31), 100),  # day before range: excluded
        row("in1", date(2025, 1, 1), 1, "1.00"),  # Wed, first week
        row("in2", date(2025, 1, 5), 1, "2.00"),  # Sun, first week
        row("in3", date(2025, 1, 6), 1, "4.00"),  # Mon, second week
        row("in4", date(2025, 3, 31), 1, "8.00"),  # Mon, last week
        row("in5", date(2025, 4, 1), 1, "16.00"),  # Tue = end, last week
        row("out3", date(2025, 4, 2), 100),  # day after range: excluded
    ]
    result = trend_for(tmp_path, rows, start, end)
    assert result["granularity"] == "weekly"
    buckets = result["buckets"]
    assert buckets[0] == {"bucket_start": date(2024, 12, 30), "gross_sales": Decimal("3")}
    assert buckets[1] == {"bucket_start": date(2025, 1, 6), "gross_sales": Decimal("4")}
    assert buckets[-1] == {"bucket_start": date(2025, 3, 31), "gross_sales": Decimal("24")}
    assert all(b["bucket_start"].weekday() == 0 for b in buckets)
    for earlier, later in zip(buckets, buckets[1:], strict=False):
        assert later["bucket_start"] - earlier["bucket_start"] == timedelta(days=7)


def test_monthly_partial_first_and_last_month(tmp_path):
    start, end = date(2024, 1, 15), date(2026, 2, 10)  # > 730 days
    rows = [
        row("out1", date(2024, 1, 14), 100),
        row("in1", date(2024, 1, 15), 1, "1.00"),
        row("in2", date(2024, 1, 31), 1, "2.00"),
        row("in3", date(2024, 2, 29), 1, "4.00"),
        row("in4", date(2026, 2, 10), 1, "8.00"),
        row("out2", date(2026, 2, 11), 100),
    ]
    result = trend_for(tmp_path, rows, start, end)
    assert result["granularity"] == "monthly"
    buckets = result["buckets"]
    assert buckets[0] == {"bucket_start": date(2024, 1, 1), "gross_sales": Decimal("3")}
    assert buckets[1] == {"bucket_start": date(2024, 2, 1), "gross_sales": Decimal("4")}
    assert buckets[-1] == {"bucket_start": date(2026, 2, 1), "gross_sales": Decimal("8")}
    assert len(buckets) == 26
    assert all(b["bucket_start"].day == 1 for b in buckets)
    # December to January rollover is contiguous
    starts = [b["bucket_start"] for b in buckets]
    assert date(2024, 12, 1) in starts and date(2025, 1, 1) in starts


def test_buckets_sum_to_kpi_gross_sales(tmp_path):
    rows = [
        row("A", date(2025, 1, 3), 3, "0.10"),
        row("A", date(2025, 1, 3), 1, "10.3333"),
        row("B", date(2025, 2, 20), 7, "0.07"),
        row("C", date(2025, 6, 1), 1, "99.9999"),
        row("D", date(2024, 12, 31), 5, "1.00"),
    ]
    connection = build(tmp_path / "sum.duckdb", rows)
    try:
        for start, end in [
            (date(2025, 1, 1), date(2025, 1, 31)),
            (date(2025, 1, 1), date(2025, 6, 30)),
            (date(2023, 1, 1), date(2025, 12, 31)),
        ]:
            result = read_trend(connection, start, end)
            total = sum((b["gross_sales"] for b in result["buckets"]), Decimal("0"))
            assert total == read_kpis(connection, start, end)["gross_sales"]
    finally:
        connection.close()


def test_money_is_exact_decimal(tmp_path):
    rows = [row(f"O{i}", date(2025, 1, 1), 1, "0.10") for i in range(3)]
    day = date(2025, 1, 1)
    bucket = trend_for(tmp_path, rows, day, day)["buckets"][0]
    assert type(bucket["gross_sales"]) is Decimal
    assert str(bucket["gross_sales"]) == "0.3000"


def test_start_after_end_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        trend_for(tmp_path, [], date(2025, 1, 2), date(2025, 1, 1))


def test_dates_are_bound_parameters():
    source = inspect.getsource(trend)
    assert "BETWEEN ? AND ?" in source
    assert 'f"' not in source and "f'" not in source and ".format(" not in source
