"""Generate the fixed-shape CSV used by the Phase 3 benchmark.

The generator is deliberately independent of the application data.  It writes
only to the path supplied by the caller and never creates a file in the
repository implicitly.

Usage::

    uv run python backend/scripts/generate_benchmark_data.py --output /tmp/osa-benchmark.csv
"""

import argparse
import csv
import random
from calendar import monthrange
from datetime import date
from pathlib import Path

DEFAULT_SEED = 20251019
DEFAULT_ROWS = 500_000
START = date(2024, 1, 1)
END = date(2025, 12, 31)
PRODUCT_COUNT = 240
CUSTOMER_COUNT = 1_200
ORDER_COUNT = 400_000

HEADER = [
    "order_id",
    "order_date",
    "product_id",
    "product_name",
    "quantity",
    "unit_price",
    "customer_id",
]


def _line_counts(rows: int) -> list[int]:
    """Return 400,000 order sizes with 500,000 lines and 100,000 multi-line orders."""
    if rows != DEFAULT_ROWS:
        # Keep the small-file path useful for tests while retaining the same
        # general shape and exact requested row count.
        multi = max(1, rows // 4)
        large = min(5, multi) if rows >= 505 else 0
        two_line = multi - large
        singles = rows - large * 101 - two_line * 2
        if singles < 1:
            raise ValueError("rows must be large enough to contain the benchmark shape")
        return [101] * large + [2] * two_line + [1] * singles
    return [101] * 5 + [2] * 99_995 + [1] * 299_505


def _customer(index: int) -> str:
    return f"C-{index:04x}"


def generate(seed: int = DEFAULT_SEED, rows: int = DEFAULT_ROWS, without_customer_id: bool = False) -> bytes:
    """Return deterministic benchmark CSV bytes for ``seed`` and ``rows``."""
    if rows < 1:
        raise ValueError("rows must be positive")
    counts = _line_counts(rows)
    rng = random.Random(seed)
    products = [(f"P-{index:03d}", f"Product {index:03d}") for index in range(PRODUCT_COUNT)]
    weights = [1 / (index + 1) ** 1.1 for index in range(PRODUCT_COUNT)]
    header = HEADER[:-1] if without_customer_id else HEADER

    output: list[str] = []
    output.append(",".join(header) + "\n")
    for order_number, line_count in enumerate(counts, start=1):
        month_index = (order_number - 1) % 24
        year = START.year + (START.month - 1 + month_index) // 12
        month = (START.month - 1 + month_index) % 12 + 1
        day = (order_number * 17) % monthrange(year, month)[1] + 1
        order_day = date(year, month, day).isoformat()
        order_id = f"O-{order_number:07d}"
        identified = order_number % 20 < 17
        # The first 1,200 identified orders establish one customer in each
        # deterministic acquisition sequence; later orders repeat them.
        customer_index = (order_number - 1) % CUSTOMER_COUNT
        customer_id = _customer(customer_index) if identified else ""
        if order_number <= CUSTOMER_COUNT:
            customer_id = _customer(order_number - 1)

        if line_count > 100:
            product_indices = list(range(101))
        else:
            product_indices = []
            while len(product_indices) < line_count:
                product = rng.choices(range(PRODUCT_COUNT), weights=weights, k=1)[0]
                if product not in product_indices:
                    product_indices.append(product)

        for line_number, product_index in enumerate(product_indices):
            product_id, product_name = products[product_index]
            quantity = 1 + rng.randrange(5)
            unit_price = 5 + (product_index * 7 + rng.randrange(900)) / 100
            row = [
                order_id,
                order_day,
                product_id,
                product_name,
                str(quantity),
                f"{unit_price:.2f}",
            ]
            if not without_customer_id:
                row.append(customer_id)
            output.append(",".join(row) + "\n")
    return "".join(output).encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="deterministic seed (default: 20251019)")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS, help="data rows (default: 500000)")
    parser.add_argument("--output", type=Path, required=True, help="destination CSV path")
    parser.add_argument(
        "--without-customer-id",
        action="store_true",
        help="write the original six-column shape",
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(generate(args.seed, args.rows, args.without_customer_id))


if __name__ == "__main__":
    main()
