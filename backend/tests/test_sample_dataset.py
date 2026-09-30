import csv
import hashlib
import importlib.util
import io
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "generate_sample.py"
COMMITTED = BACKEND / "app" / "sample" / "sample_sales.csv"

_spec = importlib.util.spec_from_file_location("generate_sample", SCRIPT)
generate_sample = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(generate_sample)


@pytest.fixture(scope="module")
def raw() -> bytes:
    return COMMITTED.read_bytes()


@pytest.fixture(scope="module")
def rows(raw):
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8"), newline="")))


def test_generated_bytes_match_the_committed_file(raw):
    generated = generate_sample.generate()

    assert hashlib.sha256(generated).hexdigest() == hashlib.sha256(raw).hexdigest()


def test_script_run_twice_gives_identical_files(tmp_path):
    first, second = tmp_path / "a.csv", tmp_path / "b.csv"
    for target in (first, second):
        subprocess.run(
            [sys.executable, str(SCRIPT), "--output", str(target)], check=True, timeout=60
        )

    assert first.read_bytes() == second.read_bytes() == COMMITTED.read_bytes()


def test_different_seed_gives_different_bytes(raw):
    assert generate_sample.generate(seed=1) != raw


def test_header_is_exactly_the_six_columns(raw):
    first_line = raw.split(b"\n", 1)[0]

    assert first_line == b"order_id,order_date,product_id,product_name,quantity,unit_price"


def test_utf8_no_bom_and_unix_line_endings(raw):
    raw.decode("utf-8")
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in raw
    assert raw.endswith(b"\n")


def test_size_is_under_5_mb(raw):
    assert len(raw) < 5 * 1024 * 1024


def test_order_and_product_counts(rows):
    assert 9_500 <= len({r["order_id"] for r in rows}) <= 10_500
    assert 25 <= len({r["product_id"] for r in rows}) <= 50


def test_dates_are_iso_within_2025_and_cover_every_month(rows):
    dates = []
    for r in rows:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", r["order_date"])
        dates.append(date.fromisoformat(r["order_date"]))

    assert min(dates) >= date(2025, 1, 1)
    assert max(dates) <= date(2025, 12, 31)
    assert {d.month for d in dates} == set(range(1, 13))


def test_at_least_20_percent_of_orders_have_several_lines(rows):
    lines_per_order = Counter(r["order_id"] for r in rows)
    multi = sum(1 for count in lines_per_order.values() if count > 1)

    assert multi / len(lines_per_order) >= 0.20


def test_order_product_pairs_are_unique(rows):
    pairs = [(r["order_id"], r["product_id"]) for r in rows]

    assert len(pairs) == len(set(pairs))


def test_each_product_id_has_one_name(rows):
    names = defaultdict(set)
    for r in rows:
        names[r["product_id"]].add(r["product_name"])

    assert all(len(v) == 1 for v in names.values())


def test_quantities_are_positive_integers(rows):
    for r in rows:
        assert re.fullmatch(r"[1-9]\d*", r["quantity"])


def test_prices_are_positive_with_at_most_two_decimals(rows):
    for r in rows:
        assert re.fullmatch(r"\d+(\.\d{1,2})?", r["unit_price"])
        assert Decimal(r["unit_price"]) > 0


def test_a_product_is_sold_at_several_prices(rows):
    prices = defaultdict(set)
    for r in rows:
        prices[r["product_id"]].add(r["unit_price"])

    assert any(len(v) >= 2 for v in prices.values())


def test_popularity_is_uneven(rows):
    units = Counter()
    for r in rows:
        units[r["product_id"]] += int(r["quantity"])

    assert max(units.values()) >= 5 * min(units.values())


def test_seasonality_between_months(rows):
    sales = Counter()
    for r in rows:
        month = int(r["order_date"][5:7])
        sales[month] += int(r["quantity"]) * Decimal(r["unit_price"])

    assert max(sales.values()) >= Decimal("1.5") * min(sales.values())


def test_weekly_pattern(rows):
    order_dates = {r["order_id"]: date.fromisoformat(r["order_date"]) for r in rows}
    per_weekday = Counter(d.weekday() for d in order_dates.values())

    assert max(per_weekday.values()) >= 1.2 * min(per_weekday.values())


def test_no_personal_data_columns(rows):
    assert set(rows[0]) == {
        "order_id", "order_date", "product_id", "product_name", "quantity", "unit_price",
    }
