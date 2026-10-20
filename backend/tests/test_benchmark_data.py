import csv
import io

from app.validation import stage_csv, validate_rows, validate_structure
from scripts.generate_benchmark_data import HEADER, generate


def test_benchmark_generator_is_byte_stable_and_seeded():
    first = generate(seed=7, rows=2_000)
    second = generate(seed=7, rows=2_000)
    other = generate(seed=8, rows=2_000)

    assert first == second
    assert first != other
    assert first.startswith((",".join(HEADER) + "\n").encode())
    assert not first.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in first
    assert first.count(b"\n") == 2_001


def test_benchmark_generator_has_the_required_shape_and_passes_validation(tmp_path):
    path = tmp_path / "benchmark.csv"
    path.write_bytes(generate(seed=11, rows=4_000))

    with path.open(newline="", encoding="utf-8") as handle:
        records = list(csv.DictReader(handle))
    assert len(records) == 4_000
    assert set(records[0]) == set(HEADER)
    assert len({row["product_id"] for row in records}) >= 200
    order_sizes: dict[str, int] = {}
    identified_orders: set[str] = set()
    for row in records:
        order_sizes[row["order_id"]] = order_sizes.get(row["order_id"], 0) + 1
        if row["customer_id"]:
            identified_orders.add(row["order_id"])
    assert sum(size > 1 for size in order_sizes.values()) / len(order_sizes) >= 0.20
    assert len(identified_orders) / len(order_sizes) >= 0.80
    assert len({row["customer_id"] for row in records if row["customer_id"]}) >= 500
    assert all(row["customer_id"].startswith("C-") for row in records if row["customer_id"])

    result = validate_structure(path, max_upload_bytes=52_428_800, max_rows=500_000)
    assert result.ok, result.to_dict()
    staging = stage_csv(path)
    try:
        rows = validate_rows(staging)
        assert rows.ok, rows.to_dict()
    finally:
        staging.close()


def test_benchmark_generator_can_omit_customer_id_without_changing_rows():
    with_customer = list(csv.reader(io.StringIO(generate(seed=3, rows=200).decode())))
    without_customer = list(
        csv.reader(io.StringIO(generate(seed=3, rows=200, without_customer_id=True).decode()))
    )

    assert with_customer[0] == HEADER
    assert without_customer[0] == HEADER[:-1]
    assert [row[:6] for row in with_customer[1:]] == without_customer[1:]
