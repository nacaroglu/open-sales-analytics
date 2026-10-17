from pathlib import Path

from app.analytics.shared.metrics import BASKET_MIN_SHARED_ORDERS, BASKET_MIN_SUPPORT, DORMANCY_WINDOWS, MAX_DISTINCT_PRODUCTS_PER_ORDER, get_metric


PRODUCT_METRICS = (
    "gross_sales_share",
    "cumulative_share",
    "top_20_percent_share",
    "products_to_80_percent",
    "product_growth",
    "rising_products",
    "falling_products",
    "dormancy",
    "weighted_unit_price",
    "order_penetration",
    "basket_support",
    "basket_confidence",
    "basket_lift",
)


def test_product_analytics_documentation_contains_metric_keys_and_labels() -> None:
    readme = (Path(__file__).parents[2] / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Product analytics", 1)[1].split("## Configuration", 1)[0]
    for key in PRODUCT_METRICS:
        metric = get_metric(key)
        assert f"`{key}`" in section
        assert metric.label in section
    assert f"{BASKET_MIN_SHARED_ORDERS} shared orders" in section
    assert "0.1% support" in section
    assert f"more than {MAX_DISTINCT_PRODUCTS_PER_ORDER} distinct" in section
    for window in DORMANCY_WINDOWS:
        assert str(window) in section
