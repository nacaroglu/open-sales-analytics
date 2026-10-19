"""Deterministic, dataset-relative RFM quintile scores and named segments."""

from datetime import date
from decimal import Decimal
from typing import TypedDict

import duckdb

from app.analytics.customers.buckets import (
    PURCHASE_FREQUENCY_BUCKETS,
    RFM_RECENCY_BUCKETS,
    frequency_bucket_key,
    recency_bucket_key,
)
from app.analytics.shared.metrics import RFM_SEGMENTS


class RfmScore(TypedDict):
    """One anonymous customer's RFM inputs, scores and segment (no customer ID)."""

    recency_days: int
    frequency: int
    monetary: Decimal
    r: int
    f: int
    m: int
    segment: str


class RfmResult(TypedDict):
    customer_count: int
    segment_counts: dict[str, int]


class RfmDrilldownSegment(TypedDict):
    """Aggregates of one segment; bucket counts are keyed in bucket order."""

    segment: str
    customer_count: int
    gross_sales: Decimal
    recency_counts: dict[str, int]
    frequency_counts: dict[str, int]


class RfmDrilldownResult(TypedDict):
    customer_count: int
    gross_sales: Decimal
    segments: list[RfmDrilldownSegment]


def rfm_score(worse: int, ties: int, n: int) -> int:
    """``floor(5 × (2 × worse + ties) / (2 × N)) + 1`` in integer arithmetic (1-5).

    ``worse`` counts customers with a strictly worse value, ``ties`` those with the same
    value (the customer included) and ``n`` the population size.
    """
    if n < 1 or ties < 1 or worse < 0 or worse + ties > n:
        raise ValueError("need 0 <= worse, 1 <= ties and worse + ties <= n")
    return (5 * (2 * worse + ties)) // (2 * n) + 1


def rfm_segment(r: int, f: int, m: int) -> str:
    """The first segment of ``RFM_SEGMENTS`` whose rule matches the scores."""
    for segment in RFM_SEGMENTS:
        if segment.matches(r, f, m):
            return segment.name
    raise ValueError(f"scores out of range: R={r}, F={f}, M={m}")


# Per customer: inputs plus, per dimension, the strictly-worse count (rank over the
# worst-first order, minus one) and the tie count. Ranks are tie-stable, so the result
# does not depend on customer IDs or row order. Customer IDs never leave the SQL.
_INPUTS_SQL = """
WITH inputs AS (
    SELECT date_diff('day', max(li.order_date), ?) AS recency_days,
           count(DISTINCT li.order_id) AS frequency,
           sum(li.quantity * li.unit_price) AS monetary
    FROM line_items AS li
    JOIN customer_facts AS cf ON cf.customer_id = li.customer_id
    WHERE li.customer_id IS NOT NULL
      AND li.order_date <= ?
      AND cf.first_order_date <= ?
    GROUP BY li.customer_id
)
SELECT recency_days, frequency, monetary,
       rank() OVER (ORDER BY recency_days DESC) - 1,
       count(*) OVER (PARTITION BY recency_days),
       rank() OVER (ORDER BY frequency ASC) - 1,
       count(*) OVER (PARTITION BY frequency),
       rank() OVER (ORDER BY monetary ASC) - 1,
       count(*) OVER (PARTITION BY monetary),
       count(*) OVER ()
FROM inputs
ORDER BY recency_days, frequency, monetary
"""


def read_rfm_scores(connection: duckdb.DuckDBPyConnection, end: date) -> list[RfmScore]:
    """Anonymous per-customer RFM scores through ``end``, for backend use only.

    The population is identified customers with an identified line dated on or before
    ``end``; all their identified lines on or before ``end`` count (the range start has
    no effect). Recency is measured to ``end``. The list is ordered by the inputs, not by
    customer, and carries no customer ID.
    """
    scores: list[RfmScore] = []
    for (
        recency_days,
        frequency,
        monetary,
        r_worse,
        r_ties,
        f_worse,
        f_ties,
        m_worse,
        m_ties,
        n,
    ) in connection.execute(_INPUTS_SQL, [end, end, end]).fetchall():
        r = rfm_score(int(r_worse), int(r_ties), int(n))
        f = rfm_score(int(f_worse), int(f_ties), int(n))
        m = rfm_score(int(m_worse), int(m_ties), int(n))
        scores.append(
            {
                "recency_days": int(recency_days),
                "frequency": int(frequency),
                "monetary": Decimal(monetary),
                "r": r,
                "f": f,
                "m": m,
                "segment": rfm_segment(r, f, m),
            }
        )
    return scores


def read_rfm(connection: duckdb.DuckDBPyConnection, end: date) -> RfmResult:
    """Population size and customers per segment, in ``RFM_SEGMENTS`` order."""
    scores = read_rfm_scores(connection, end)
    counts = {segment.name: 0 for segment in RFM_SEGMENTS}
    for score in scores:
        counts[score["segment"]] += 1
    return {"customer_count": len(scores), "segment_counts": counts}


def rfm_drilldown(scores: list[RfmScore]) -> RfmDrilldownResult:
    """Aggregate anonymous scores per segment: counts, exact gross sales, distributions.

    Every segment of ``RFM_SEGMENTS`` and every bucket is present, in fixed order, even
    when empty. Only aggregates are returned.
    """
    segments: dict[str, RfmDrilldownSegment] = {
        segment.name: {
            "segment": segment.name,
            "customer_count": 0,
            "gross_sales": Decimal(0),
            "recency_counts": {bucket.key: 0 for bucket in RFM_RECENCY_BUCKETS},
            "frequency_counts": {bucket.key: 0 for bucket in PURCHASE_FREQUENCY_BUCKETS},
        }
        for segment in RFM_SEGMENTS
    }
    total = Decimal(0)
    for score in scores:
        group = segments[score["segment"]]
        group["customer_count"] += 1
        group["gross_sales"] += score["monetary"]
        group["recency_counts"][recency_bucket_key(score["recency_days"])] += 1
        group["frequency_counts"][frequency_bucket_key(score["frequency"])] += 1
        total += score["monetary"]
    return {
        "customer_count": len(scores),
        "gross_sales": total,
        "segments": list(segments.values()),
    }


def read_rfm_drilldown(connection: duckdb.DuckDBPyConnection, end: date) -> RfmDrilldownResult:
    """Per-segment aggregates of ``read_rfm_scores`` through ``end`` (no customer IDs)."""
    return rfm_drilldown(read_rfm_scores(connection, end))
