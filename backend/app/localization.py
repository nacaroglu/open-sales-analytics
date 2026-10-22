"""Language-neutral metadata used by clients to localize retained English copy."""

import re

_KNOWN_REASONS = {
    "The file has no customer_id column.": "customers.no_customer_id",
    "No orders in the selected range.": "customers.no_orders",
    "No products have sales in the selected range.": "products.no_sales",
    "Gross sales in this range are zero.": "products.zero_gross_sales",
    "No products have sales in the selected ranges.": "products.no_comparison_sales",
    "No dormant products in the selected range.": "products.no_dormant_products",
    "No eligible product pairs in the selected range.": "products.no_product_pairs",
    "No eligible related products in the selected range.": "products.no_related_products",
    "All orders in this range have more than 100 products and are excluded from basket analysis": "products.basket.all_orders_oversized",
    "At least 10 orders are needed for basket analysis": "products.basket.minimum_orders",
    "A comparison needs at least two days of history.": "comparison.needs_two_days",
    "No identified customers placed an order in the selected range.": "customers.no_identified_orders",
    "No identified customer rows were found in the selected range.": "customers.no_identified_rows",
    "No active identified customer had two or more orders by the end of the range.": "customers.no_repeat_customers",
    "No identified customer placed a repeat order in the selected range, so there is no interval between purchases.": "customers.no_purchase_intervals",
    "No identified customer was acquired in a month that overlaps the selected range, so there is no acquisition cohort.": "customers.no_acquisition_cohort",
    "No identified customer was acquired in a month that overlaps the selected range, so there is no customer whose value can be observed.": "customers.no_observed_customer_value",
    "The identified customers acquired in the selected months have no gross sales up to the end of the range.": "customers.zero_historical_value",
    "No identified customers placed an order on or before the selected end date.": "customers.no_customers_before_end",
    "Concentration needs at least 10 identified customers in the range.": "customers.concentration.minimum_customers",
    "Concentration is undefined when identified gross sales are zero.": "customers.concentration.zero_sales",
    "The projection eligibility requirements are not met.": "customers.projection.requirements_not_met",
    "Projection eligibility requires a customer_id column.": "customers.projection.missing_customer_id",
}


def reason_code(reason: str | None, prefix: str = "availability") -> str | None:
    """Return a stable dotted identifier for retained English fallback copy."""
    if reason is None:
        return None
    known = _KNOWN_REASONS.get(reason)
    if known is not None:
        return known
    return f"{prefix}.unknown"


def localized_reason(reason: str | None, prefix: str = "availability") -> dict:
    if reason is None:
        return {"reason_code": None, "reason_params": {}}
    patterns = (
        (r"The comparison needs data from ([0-9-]+), but the dataset starts on ([0-9-]+)\.",
         "comparison.outside_dataset", ("comparison_start", "dataset_start")),
        (r"The data covers fewer than (\d+) days before ([0-9-]+)\.",
         "products.insufficient_dormancy_history", ("window_days", "anchor_date")),
        (r"RFM needs at least (\d+) identified customers\.",
         "customers.rfm.minimum_customers", ("minimum_customers",)),
        (r"Only ([0-9,]+) of ([0-9,]+) orders \((\d+)%\) have a customer_id; customer results describe those orders only\.",
         "customers.low_coverage", ("identified_orders", "total_orders", "coverage_percent")),
        (r"Customer analytics needs a customer_id on at least (\d+)% of orders; ([0-9,]+) of ([0-9,]+) orders \((\d+)%\) have one\.",
         "customers.coverage_below_threshold", ("minimum_coverage_percent", "identified_orders", "total_orders", "coverage_percent")),
    )
    for pattern, code, names in patterns:
        match = re.fullmatch(pattern, reason)
        if match:
            params = {}
            for name, raw in zip(names, match.groups(), strict=True):
                params[name] = int(raw.replace(",", "")) if raw.replace(",", "").isdigit() else raw
            return {"reason_code": code, "reason_params": params}
    return {"reason_code": _KNOWN_REASONS.get(reason, reason_code(reason, prefix)), "reason_params": {}}


def validation_reason_params(code: str, reason: str, field: str | None) -> dict:
    """Extract scalar values needed by the frontend's validation translations.

    The original English reason remains in the response for compatibility. Values
    quoted from a CSV stay data and are rendered as text by the frontend.
    """
    if code in {"missing_value", "missing_column", "extra_column"}:
        return {"field": field} if field is not None else {}
    if code == "duplicate_column":
        match = re.fullmatch(r"The column '(.+)' appears (\d+) times\.", reason)
        return {"field": field or match.group(1), "count": int(match.group(2))} if match else {}
    if code == "file_too_large":
        match = re.fullmatch(r"The file is larger than the (.+) limit\.", reason)
        return {"limit": match.group(1)} if match else {}
    if code == "too_many_rows":
        match = re.fullmatch(r"The file has more than the ([0-9,]+) data rows allowed\.", reason)
        return {"max_rows": int(match.group(1).replace(",", ""))} if match else {}
    if code == "future_date":
        match = re.fullmatch(r"The order date '(.+)' is in the future\.", reason)
        return {"value": match.group(1)} if match else {}
    if code in {"invalid_date", "invalid_quantity", "invalid_price", "negative_price"}:
        match = re.search(r"(?:got |future, got )'?(.*?)'?\.?$", reason)
        return {"value": match.group(1)} if match else {}
    if code == "line_total_too_large":
        match = re.fullmatch(r"quantity × unit_price must be less than ([0-9,]+), got (.+) × (.+)\.", reason)
        return {"limit": int(match.group(1).replace(",", "")), "quantity": match.group(2), "unit_price": match.group(3)} if match else {}
    if code == "malformed_row":
        match = re.fullmatch(r"The row has (\d+) values but the header has (\d+)\.", reason)
        return {"values": int(match.group(1)), "header_values": int(match.group(2))} if match else {}
    if code == "duplicate_line":
        match = re.fullmatch(r"This order and product already appear on row (\d+)\.", reason)
        return {"first_row": int(match.group(1))} if match else {}
    if code == "zero_price":
        match = re.fullmatch(r"([0-9,]+) lines? (?:have|has) a unit price of 0\.", reason)
        return {"count": int(match.group(1).replace(",", ""))} if match else {}
    if code == "conflicting_customer_id":
        match = re.fullmatch(r"Order '(.+)' has (\d+) different customer IDs\.", reason)
        return {"order_id": match.group(1), "count": int(match.group(2))} if match else {}
    if code == "conflicting_product_name":
        match = re.fullmatch(
            r"Product '(.*)' has (\d+) different names; the first two are '(.*)' and '(.*)'\.",
            reason,
        )
        return (
            {
                "product_id": match.group(1),
                "count": int(match.group(2)),
                "first_name": match.group(3),
                "second_name": match.group(4),
            }
            if match
            else {}
        )
    return {}
