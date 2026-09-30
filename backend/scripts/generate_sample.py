"""Generate the bundled synthetic sales CSV.

The output is a pure function of the seed: same seed, same bytes. The date
window is fixed (calendar year 2025) rather than derived from today's date, so
the committed file never goes stale.

Usage: uv run python backend/scripts/generate_sample.py [--seed N] [--output PATH]
"""

import argparse
import csv
import io
import random
from datetime import date, timedelta
from pathlib import Path

DEFAULT_SEED = 20250101
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "app" / "sample" / "sample_sales.csv"

HEADER = ["order_id", "order_date", "product_id", "product_name", "quantity", "unit_price"]
ORDER_COUNT = 10_000
START = date(2025, 1, 1)
END = date(2025, 12, 31)

# (product name, base price in cents)
PRODUCTS = [
    ("Ceramic Mug", 1200),
    ("Travel Tumbler", 2400),
    ("Linen Tote Bag", 1800),
    ("Canvas Backpack", 5900),
    ("Wool Beanie", 2200),
    ("Cotton T-Shirt", 2500),
    ("Denim Jacket", 8900),
    ("Running Socks", 1100),
    ("Leather Wallet", 4500),
    ("Steel Water Bottle", 2000),
    ("Bamboo Cutting Board", 3200),
    ("Chef Knife", 7400),
    ("Cast Iron Pan", 5600),
    ("Scented Candle", 1600),
    ("Soy Wax Candle Set", 3400),
    ("Desk Lamp", 4900),
    ("Notebook A5", 900),
    ("Fountain Pen", 3800),
    ("Wireless Mouse", 2900),
    ("Laptop Stand", 4200),
    ("USB-C Cable", 1000),
    ("Phone Case", 1500),
    ("Bluetooth Speaker", 6900),
    ("Yoga Mat", 3600),
    ("Resistance Bands", 1400),
    ("Herbal Tea Sampler", 1900),
    ("Coffee Beans 1kg", 2800),
    ("Olive Oil 500ml", 2100),
    ("Hot Sauce Trio", 2300),
    ("Wall Calendar", 1300),
    ("Framed Print", 6400),
    ("Throw Pillow", 2700),
    ("Wool Blanket", 7900),
    ("Sunglasses", 4600),
    ("Umbrella", 2600),
    ("Gift Card Holder", 700),
]

# Zipf-like popularity: a few best-sellers, a long tail.
PRODUCT_WEIGHTS = [1 / (rank + 1) ** 1.1 for rank in range(len(PRODUCTS))]

# Seasonality: quiet start of year, strong November/December.
MONTH_FACTOR = {
    1: 0.8,
    2: 0.8,
    3: 0.9,
    4: 0.95,
    5: 1.0,
    6: 1.0,
    7: 0.95,
    8: 0.95,
    9: 1.0,
    10: 1.1,
    11: 1.6,
    12: 1.8,
}
# Weekly pattern, Monday=0: busier weekends, quiet midweek.
WEEKDAY_FACTOR = {0: 1.0, 1: 0.9, 2: 0.8, 3: 0.9, 4: 1.1, 5: 1.4, 6: 1.3}

LINES_PER_ORDER = ([1, 2, 3, 4], [70, 20, 7, 3])
QUANTITIES = ([1, 2, 3, 4, 5], [60, 22, 10, 5, 3])
PRICE_FACTORS = ([90, 100, 110], [15, 70, 15])  # percent of base price


def _days() -> list[date]:
    return [START + timedelta(days=i) for i in range((END - START).days + 1)]


def _cents(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def generate(seed: int = DEFAULT_SEED) -> bytes:
    rng = random.Random(seed)
    days = _days()
    day_weights = [MONTH_FACTOR[d.month] * WEEKDAY_FACTOR[d.weekday()] for d in days]
    order_days = sorted(rng.choices(days, weights=day_weights, k=ORDER_COUNT))

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADER)

    indexes = list(range(len(PRODUCTS)))
    for number, order_day in enumerate(order_days, start=1):
        order_id = f"ORD-{number:06d}"
        line_count = rng.choices(*LINES_PER_ORDER)[0]
        chosen: list[int] = []
        while len(chosen) < line_count:
            pick = rng.choices(indexes, weights=PRODUCT_WEIGHTS)[0]
            if pick not in chosen:
                chosen.append(pick)
        for index in sorted(chosen):
            name, base_cents = PRODUCTS[index]
            quantity = rng.choices(*QUANTITIES)[0]
            percent = rng.choices(*PRICE_FACTORS)[0]
            price = _cents(round(base_cents * percent / 100))
            writer.writerow(
                [order_id, order_day.isoformat(), f"P{index + 1:03d}", name, quantity, price]
            )
    return buffer.getvalue().encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(generate(args.seed))


if __name__ == "__main__":
    main()
