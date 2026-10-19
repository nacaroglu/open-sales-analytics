import json
from datetime import UTC, datetime

import pytest
from app.auth import get_now
from app.config import Settings, get_settings
from app.main import app
from app.response_cache import ResponseCache, get_response_cache
from fastapi.testclient import TestClient

REQUIRED = "order_id,order_date,product_id,product_name,quantity,unit_price"
CUSTOMER_HEADER = REQUIRED + ",customer_id"
NOW = datetime(2025, 1, 20, tzinfo=UTC)


@pytest.fixture
def settings(tmp_path):
    return Settings(DATASET_DIR=tmp_path / "data", DATASET_TTL_HOURS=24)


@pytest.fixture
def client(settings):
    cache = ResponseCache(max_entries=20, ttl_seconds=300)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_now] = lambda: NOW
    app.dependency_overrides[get_response_cache] = lambda: cache
    yield TestClient(app)
    app.dependency_overrides.clear()


def upload(client, rows, header=CUSTOMER_HEADER):
    csv = header + "\n" + "\n".join(rows) + "\n"
    response = client.post(
        "/api/datasets",
        files={"file": ("customers.csv", csv.encode(), "text/csv")},
        data={"currency": "EUR"},
    )
    assert response.status_code == 201
    return response.json()


def get_customers(client, dataset, **params):
    return client.get(
        f"/api/datasets/{dataset['dataset_id']}/customers",
        params=params,
        headers={"Authorization": f"Bearer {dataset['token']}"},
    )


def test_customers_returns_typed_aggregate_envelope_and_range_coverage(client, capsys):
    dataset = upload(
        client,
        [
            "o1,2025-01-01,p1,Mug,1,2.00,CUSTMARKER-0001",
            "o2,2025-01-02,p1,Mug,1,3.00,CUSTMARKER-0002",
            "o3,2025-01-03,p1,Mug,1,4.00,",
            "o4,2025-01-04,p1,Mug,1,5.00,CUSTMARKER-0002",
        ],
    )
    response = get_customers(client, dataset, start="2025-01-02", end="2025-01-03")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert body["module"] == "customers"
    assert body["currency"] == "EUR"
    assert body["availability"] == {
        "tier": "warning",
        "state": "available",
        "reason": None,
        "warning": {
            "state": "low_coverage",
            "reason": "Only 3 of 4 orders (75%) have a customer_id; customer results describe those orders only.",
        },
    }
    assert body["coverage"] == {
        "dataset": {
            "tier": "warning",
            "coverage": 0.75,
            "identified_orders": 3,
            "unidentified_orders": 1,
            "total_orders": 4,
        },
        "range": {
            "tier": "warning",
            "coverage": 0.5,
            "identified_orders": 1,
            "unidentified_orders": 1,
            "total_orders": 2,
        },
    }
    assert body["sections"]["identified_customers"] == {
        "availability": {"state": "available", "reason": None},
        "value": {
            "value": 1,
            "comparison_value": None,
            "absolute_change": None,
            "percent_change": None,
            "change_status": None,
        },
    }
    unavailable_comparison = {
        "comparison_value": None,
        "absolute_change": None,
        "percent_change": None,
        "change_status": None,
    }
    assert body["sections"]["new_vs_returning"] == {
        "availability": {"state": "available", "reason": None},
        "new_customer_gross_sales": {"value": "3.0000", **unavailable_comparison},
        "returning_customer_gross_sales": {"value": "0.0000", **unavailable_comparison},
        "identified_gross_sales": {"value": "3.0000", **unavailable_comparison},
    }
    assert body["sections"]["repeat_purchase"] == {
        "availability": {
            "state": "zero_result",
            "reason": "No active identified customer had two or more orders by the end of the range.",
        },
        "active_customers": {"value": 1, **unavailable_comparison},
        "repeat_customers": {"value": 0, **unavailable_comparison},
        "repeat_purchase_rate": {"value": 0, **unavailable_comparison},
    }
    assert body["sections"]["days_between_purchases"]["interval_count"] == 0
    with_interval = get_customers(client, dataset, start="2025-01-02", end="2025-01-04")
    days = with_interval.json()["sections"]["days_between_purchases"]
    assert days["availability"] == {"state": "available", "reason": None}
    assert (days["median_days"], days["interval_count"], days["contributing_customers"]) == (
        2,
        1,
        1,
    )
    assert days["buckets"][1] == {
        "key": "1-7",
        "min_days": 1,
        "max_days": 7,
        "interval_count": 1,
        "share": 1,
    }
    cohorts = body["sections"]["cohort_retention"]
    assert cohorts["availability"] == {"state": "available", "reason": None}
    assert cohorts["data_cutoff"] == "2025-01-03"
    assert [(row["cohort_month"], row["cohort_size"]) for row in cohorts["rows"]] == [
        ("2025-01", 2)
    ]
    assert cohorts["rows"][0]["cells"] == [
        {"month_offset": 0, "state": "partial", "retained_count": 2, "retention": 1}
    ]
    markers = ("CUSTMARKER-0001", "CUSTMARKER-0002")
    for body_text in (response.text, with_interval.text):
        assert all(marker not in body_text for marker in markers)
    captured = capsys.readouterr()
    log_text = captured.out + captured.err
    assert all(marker not in log_text for marker in markers)


def test_identified_customers_comparison_uses_shared_change_semantics(client):
    dataset = upload(
        client,
        [
            "o1,2026-02-28,p1,Mug,1,2.00,C1",
            "o2,2026-03-01,p1,Mug,1,2.00,C1",
            "o3,2026-03-15,p1,Mug,1,2.00,C2",
        ],
    )
    response = get_customers(client, dataset, start="2026-03-01", end="2026-03-01")
    value = response.json()["sections"]["identified_customers"]["value"]
    assert value == {
        "value": 1,
        "comparison_value": 1,
        "absolute_change": 0,
        "percent_change": "0.00",
        "change_status": "comparable",
    }


def test_identified_customers_zero_result_is_available_as_a_section(client):
    dataset = upload(
        client,
        ["o1,2025-01-01,p1,Mug,1,2.00,C1", "o2,2025-01-03,p1,Mug,1,2.00,C2"],
    )
    response = get_customers(client, dataset, start="2025-01-02", end="2025-01-02")
    section = response.json()["sections"]["identified_customers"]
    assert section["availability"]["state"] == "zero_result"
    assert section["value"]["value"] == 0


GOLDEN_ROWS = [
    "a1,2026-01-10,p1,Mug,1,100.00,A",
    "a2,2026-01-10,p2,Cup,1,50.00,A",
    "a3,2026-02-05,p1,Mug,1,30.00,A",
    "b1,2026-02-05,p1,Mug,1,20.00,B",
    "b2,2026-02-20,p1,Mug,1,40.00,B",
    "u1,2026-02-10,p1,Mug,1,999.00,",
]


def test_new_vs_returning_comparison_classifies_by_first_order_date(client):
    dataset = upload(client, GOLDEN_ROWS)
    body = get_customers(client, dataset, start="2026-02-06", end="2026-02-20").json()

    assert body["comparison"]["comparison"] == {"start": "2026-01-22", "end": "2026-02-05"}
    assert body["sections"]["new_vs_returning"] == {
        "availability": {"state": "available", "reason": None},
        "new_customer_gross_sales": {
            "value": "0.0000",
            "comparison_value": "20.0000",
            "absolute_change": "-20.0000",
            "percent_change": "-100.00",
            "change_status": "comparable",
        },
        "returning_customer_gross_sales": {
            "value": "40.0000",
            "comparison_value": "30.0000",
            "absolute_change": "10.0000",
            "percent_change": "33.33",
            "change_status": "comparable",
        },
        "identified_gross_sales": {
            "value": "40.0000",
            "comparison_value": "50.0000",
            "absolute_change": "-10.0000",
            "percent_change": "-20.00",
            "change_status": "comparable",
        },
    }


def test_new_vs_returning_empty_comparison_period_has_no_prior_value(client):
    dataset = upload(client, GOLDEN_ROWS)
    body = get_customers(client, dataset, start="2026-02-01", end="2026-02-20").json()

    assert body["comparison"]["comparison"] == {"start": "2026-01-12", "end": "2026-01-31"}
    section = body["sections"]["new_vs_returning"]
    for key, value in (
        ("new_customer_gross_sales", "20.0000"),
        ("returning_customer_gross_sales", "70.0000"),
        ("identified_gross_sales", "90.0000"),
    ):
        assert section[key]["value"] == value
        assert section[key]["comparison_value"] == "0.0000"
        assert section[key]["change_status"] == "no_prior_value"
        assert section[key]["percent_change"] is None


def test_new_vs_returning_unavailable_comparison_is_not_queried(client, monkeypatch):
    import app.api.customers as customers_api

    calls = []
    original = customers_api.read_new_vs_returning

    def recording(connection, start, end):
        calls.append((start.isoformat(), end.isoformat()))
        return original(connection, start, end)

    monkeypatch.setattr(customers_api, "read_new_vs_returning", recording)
    dataset = upload(client, GOLDEN_ROWS)
    body = get_customers(client, dataset, start="2026-01-11", end="2026-02-20").json()

    assert body["comparison"]["state"] == "unavailable"
    assert calls == [("2026-01-11", "2026-02-20")]
    section = body["sections"]["new_vs_returning"]
    for key, value in (
        ("new_customer_gross_sales", "20.0000"),
        ("returning_customer_gross_sales", "70.0000"),
        ("identified_gross_sales", "90.0000"),
    ):
        assert section[key] == {
            "value": value,
            "comparison_value": None,
            "absolute_change": None,
            "percent_change": None,
            "change_status": None,
        }


def test_new_vs_returning_zero_result(client):
    dataset = upload(
        client,
        [
            "a1,2025-01-10,p1,Mug,1,100.00,C1",
            "a2,2025-02-05,p1,Mug,1,30.00,C1",
            "u1,2025-01-20,p1,Mug,1,9.00,",
        ],
    )
    body = get_customers(client, dataset, start="2025-01-11", end="2025-01-31").json()
    section = body["sections"]["new_vs_returning"]

    assert section["availability"] == {
        "state": "zero_result",
        "reason": "No identified customer rows were found in the selected range.",
    }
    for key in (
        "new_customer_gross_sales",
        "returning_customer_gross_sales",
        "identified_gross_sales",
    ):
        assert section[key]["value"] == "0.0000"


REPEAT_ROWS = [
    "a1,2026-01-10,p1,Mug,1,1.00,A",
    "a2,2026-01-10,p1,Mug,1,1.00,A",
    "a3,2026-02-05,p1,Mug,1,1.00,A",
    "b1,2026-02-05,p1,Mug,1,1.00,B",
    "b2,2026-02-20,p1,Mug,1,1.00,B",
    "c1,2026-02-10,p1,Mug,1,1.00,C",
    "c2,2026-03-03,p1,Mug,1,1.00,C",
    "d1,2026-01-05,p1,Mug,1,1.00,D",
    "e1,2026-02-12,p1,Mug,1,1.00,E",
    "e1,2026-02-12,p2,Cup,1,1.00,E",
]


def test_repeat_purchase_previous_period_compares_exact_fractions(client):
    dataset = upload(client, REPEAT_ROWS)
    body = get_customers(client, dataset, start="2026-02-11", end="2026-02-28").json()

    assert body["comparison"]["comparison"] == {"start": "2026-01-24", "end": "2026-02-10"}
    assert body["sections"]["identified_customers"]["value"]["value"] == 2
    assert body["sections"]["repeat_purchase"] == {
        "availability": {"state": "available", "reason": None},
        "active_customers": {
            "value": 2,
            "comparison_value": 3,
            "absolute_change": -1,
            "percent_change": "-33.33",
            "change_status": "comparable",
        },
        "repeat_customers": {
            "value": 1,
            "comparison_value": 1,
            "absolute_change": 0,
            "percent_change": "0.00",
            "change_status": "comparable",
        },
        "repeat_purchase_rate": {
            "value": 0.5,
            "comparison_value": 0.3333,
            "absolute_change": 0.1667,
            "percent_change": "50.00",
            "change_status": "comparable",
        },
    }


def test_repeat_purchase_unavailable_comparison_is_not_queried(client, monkeypatch):
    import app.api.customers as customers_api

    calls = []
    original = customers_api.read_repeat_purchase

    def recording(connection, start, end):
        calls.append((start.isoformat(), end.isoformat()))
        return original(connection, start, end)

    monkeypatch.setattr(customers_api, "read_repeat_purchase", recording)
    dataset = upload(client, REPEAT_ROWS)
    body = get_customers(client, dataset, start="2026-02-01", end="2026-02-28").json()

    assert body["comparison"]["comparison"]["start"] == "2026-01-04"
    assert body["comparison"]["state"] == "unavailable"
    assert calls == [("2026-02-01", "2026-02-28")]
    unavailable = {
        "comparison_value": None,
        "absolute_change": None,
        "percent_change": None,
        "change_status": None,
    }
    assert body["sections"]["identified_customers"]["value"]["value"] == 4
    assert body["sections"]["repeat_purchase"] == {
        "availability": {"state": "available", "reason": None},
        "active_customers": {"value": 4, **unavailable},
        "repeat_customers": {"value": 2, **unavailable},
        "repeat_purchase_rate": {"value": 0.5, **unavailable},
    }

    calls.clear()
    default = get_customers(client, dataset).json()
    assert default["comparison"]["state"] == "unavailable"
    assert calls == [("2026-01-05", "2026-03-03")]
    assert default["sections"]["repeat_purchase"]["repeat_purchase_rate"] == {
        "value": 0.6,
        **unavailable,
    }


def test_repeat_purchase_rounds_the_current_rate_half_up(client):
    dataset = upload(client, REPEAT_ROWS)
    body = get_customers(client, dataset, start="2026-02-01", end="2026-02-10").json()
    section = body["sections"]["repeat_purchase"]

    assert section["active_customers"]["value"] == 3
    assert section["repeat_customers"]["value"] == 1
    assert section["repeat_purchase_rate"]["value"] == 0.3333


def test_repeat_purchase_without_active_customers_is_insufficient_data(client):
    dataset = upload(
        client,
        [
            "a1,2025-01-01,p1,Mug,1,2.00,C1",
            "a2,2025-01-02,p1,Mug,1,2.00,C1",
            "u1,2025-01-10,p1,Mug,1,2.00,",
            "a3,2025-01-20,p1,Mug,1,2.00,C1",
        ],
    )
    body = get_customers(client, dataset, start="2025-01-10", end="2025-01-10").json()
    section = body["sections"]["repeat_purchase"]

    assert body["comparison"]["state"] == "available"
    assert section["availability"]["state"] == "insufficient_data"
    assert section["availability"]["reason"]
    assert section["active_customers"]["value"] == 0
    assert section["repeat_customers"]["value"] == 0
    assert section["active_customers"]["comparison_value"] == 0
    assert section["active_customers"]["change_status"] == "no_change"
    assert section["repeat_purchase_rate"] == {
        "value": None,
        "comparison_value": None,
        "absolute_change": None,
        "percent_change": None,
        "change_status": None,
    }
    assert "NaN" not in json.dumps(body)


def test_repeat_purchase_zero_comparison_population_keeps_count_changes(client):
    dataset = upload(
        client,
        [
            "a1,2025-01-01,p1,Mug,1,2.00,C1",
            "u1,2025-01-02,p1,Mug,1,2.00,",
            "a2,2025-01-03,p1,Mug,1,2.00,C1",
        ],
    )
    body = get_customers(client, dataset, start="2025-01-03", end="2025-01-03").json()
    section = body["sections"]["repeat_purchase"]

    assert body["comparison"]["comparison"] == {"start": "2025-01-02", "end": "2025-01-02"}
    assert section["availability"] == {"state": "available", "reason": None}
    assert section["active_customers"] == {
        "value": 1,
        "comparison_value": 0,
        "absolute_change": 1,
        "percent_change": None,
        "change_status": "no_prior_value",
    }
    assert section["repeat_purchase_rate"] == {
        "value": 1.0,
        "comparison_value": None,
        "absolute_change": None,
        "percent_change": None,
        "change_status": None,
    }


def test_repeat_purchase_zero_current_population_keeps_comparison_rate(client):
    dataset = upload(
        client,
        [
            "a1,2025-01-01,p1,Mug,1,2.00,C1",
            "a2,2025-01-02,p1,Mug,1,2.00,C1",
            "u1,2025-01-03,p1,Mug,1,2.00,",
        ],
    )
    body = get_customers(client, dataset, start="2025-01-03", end="2025-01-03").json()
    rate = body["sections"]["repeat_purchase"]["repeat_purchase_rate"]

    assert rate == {
        "value": None,
        "comparison_value": 1.0,
        "absolute_change": None,
        "percent_change": None,
        "change_status": None,
    }


def test_repeat_purchase_warning_tier_matches_the_identified_only_numbers(client):
    identified = [
        "a1,2025-01-01,p1,Mug,1,2.00,C1",
        "a2,2025-01-02,p1,Mug,1,2.00,C1",
        "b1,2025-01-02,p1,Mug,1,2.00,C2",
    ]
    normal = upload(client, identified)
    warning = upload(client, identified + ["u1,2025-01-02,p1,Mug,1,2.00,"])
    normal_body = get_customers(client, normal).json()
    warning_body = get_customers(client, warning).json()

    assert normal_body["availability"]["tier"] == "normal"
    assert warning_body["availability"]["tier"] == "warning"
    assert warning_body["sections"]["repeat_purchase"] == normal_body["sections"]["repeat_purchase"]
    assert normal_body["sections"]["repeat_purchase"]["repeat_purchase_rate"]["value"] == 0.5


DAYS_ROWS = [
    "a1,2026-01-10,p1,Mug,1,2.00,A",
    "a2,2026-01-10,p1,Mug,1,2.00,A",
    "a3,2026-02-05,p1,Mug,1,2.00,A",
    "a4,2026-03-07,p1,Mug,1,2.00,A",
    "b1,2026-02-05,p1,Mug,1,2.00,B",
    "b2,2026-02-20,p1,Mug,1,2.00,B",
    "c1,2026-02-10,p1,Mug,1,2.00,C",
]
DAYS_KEYS = ["0", "1-7", "8-14", "15-30", "31-60", "61-90", "91-180", "181-365", "366+"]
DAYS_LIMITS = [(0, 0), (1, 7), (8, 14), (15, 30), (31, 60), (61, 90), (91, 180), (181, 365)]


def test_days_between_purchases_has_median_and_all_nine_buckets(client):
    dataset = upload(client, DAYS_ROWS)
    days = get_customers(client, dataset, start="2026-01-10", end="2026-03-07").json()["sections"][
        "days_between_purchases"
    ]

    assert days["availability"] == {"state": "available", "reason": None}
    assert days["median_days"] == 20.5
    assert days["interval_count"] == 4
    assert days["contributing_customers"] == 2
    assert [bucket["key"] for bucket in days["buckets"]] == DAYS_KEYS
    assert [(b["min_days"], b["max_days"]) for b in days["buckets"]] == DAYS_LIMITS + [(366, None)]
    assert [b["interval_count"] for b in days["buckets"]] == [1, 0, 0, 3, 0, 0, 0, 0, 0]
    assert [b["share"] for b in days["buckets"]] == [0.25, 0, 0, 0.75, 0, 0, 0, 0, 0]
    assert set(days) == {
        "availability",
        "median_days",
        "interval_count",
        "contributing_customers",
        "buckets",
    }
    serialized = json.dumps(days)
    for field in ("comparison_value", "absolute_change", "percent_change", "change_status"):
        assert field not in serialized


def test_days_between_purchases_rounds_shares_half_up_from_exact_counts(client):
    rows = [
        "a1,2026-01-01,p1,Mug,1,2.00,A",
        "a2,2026-01-01,p1,Mug,1,2.00,A",
        "a3,2026-01-03,p1,Mug,1,2.00,A",
        "a4,2026-01-04,p1,Mug,1,2.00,A",
    ]
    dataset = upload(client, rows)
    days = get_customers(client, dataset).json()["sections"]["days_between_purchases"]

    assert days["median_days"] == 1
    assert days["buckets"][0]["share"] == 0.3333
    assert days["buckets"][1]["share"] == 0.6667


def test_days_between_purchases_is_current_range_only(client, monkeypatch):
    import app.api.customers as customers_api

    calls = []
    original = customers_api.read_days_between_purchases

    def recording(connection, start, end):
        calls.append((start.isoformat(), end.isoformat()))
        return original(connection, start, end)

    monkeypatch.setattr(customers_api, "read_days_between_purchases", recording)
    dataset = upload(client, DAYS_ROWS)
    previous = get_customers(client, dataset, start="2026-03-01", end="2026-03-07").json()
    calls_previous = list(calls)
    calls.clear()
    yoy = get_customers(
        client, dataset, start="2026-03-01", end="2026-03-07", comparison="previous_year"
    ).json()

    assert previous["comparison"]["state"] == "available"
    assert calls_previous == [("2026-03-01", "2026-03-07")]
    assert calls == [("2026-03-01", "2026-03-07")]
    assert (
        previous["sections"]["days_between_purchases"] == yoy["sections"]["days_between_purchases"]
    )
    days = previous["sections"]["days_between_purchases"]
    assert (days["median_days"], days["interval_count"], days["contributing_customers"]) == (
        30,
        1,
        1,
    )


def test_days_between_purchases_without_interval_is_insufficient_data(client):
    dataset = upload(client, DAYS_ROWS)
    days = get_customers(client, dataset, start="2026-02-06", end="2026-02-19").json()["sections"][
        "days_between_purchases"
    ]

    assert days["availability"]["state"] == "insufficient_data"
    assert days["availability"]["reason"]
    assert days["median_days"] is None
    assert days["interval_count"] == 0
    assert days["contributing_customers"] == 0
    assert [b["key"] for b in days["buckets"]] == DAYS_KEYS
    assert all(b["interval_count"] == 0 and b["share"] is None for b in days["buckets"])


def test_days_between_purchases_warning_tier_matches_normal_numbers(client):
    normal = upload(client, DAYS_ROWS)
    unidentified = [f"u{day},2026-02-{day},p1,Mug,1,2.00," for day in (11, 12, 13)]
    warning = upload(client, DAYS_ROWS + unidentified)
    normal_body = get_customers(client, normal).json()
    warning_body = get_customers(client, warning).json()

    assert normal_body["availability"]["tier"] == "normal"
    assert warning_body["availability"]["tier"] == "warning"
    assert (
        warning_body["sections"]["days_between_purchases"]
        == normal_body["sections"]["days_between_purchases"]
    )
    assert normal_body["sections"]["days_between_purchases"]["median_days"] == 20.5


COHORT_ROWS = [
    "a1,2026-01-10,p1,Mug,1,2.00,A",
    "a2,2026-02-05,p1,Mug,1,2.00,A",
    "a3,2026-03-07,p1,Mug,1,2.00,A",
    "f1,2026-01-20,p1,Mug,1,2.00,F",
    "b1,2026-02-05,p1,Mug,1,2.00,B",
    "g1,2026-02-25,p1,Mug,1,2.00,G",
    "g2,2026-03-20,p1,Mug,1,2.00,G",
    "h1,2026-03-03,p1,Mug,1,2.00,H",
    "u1,2026-03-31,p1,Mug,1,2.00,",
]


def cohort_cell(offset, state, count, retention):
    return {
        "month_offset": offset,
        "state": state,
        "retained_count": count,
        "retention": retention,
    }


NOT_OBSERVED_CELLS = [cohort_cell(n, "not_observed", None, None) for n in (1, 2)]
GOLDEN_COHORTS = [
    {
        "cohort_month": "2026-01",
        "cohort_size": 2,
        "complete_months": 2,
        "cells": [
            cohort_cell(0, "complete", 2, 1),
            cohort_cell(1, "complete", 1, 0.5),
            cohort_cell(2, "partial", 1, 0.5),
        ],
    },
    {
        "cohort_month": "2026-02",
        "cohort_size": 2,
        "complete_months": 1,
        "cells": [
            cohort_cell(0, "complete", 2, 1),
            cohort_cell(1, "partial", 0, 0),
            NOT_OBSERVED_CELLS[1],
        ],
    },
    {
        "cohort_month": "2026-03",
        "cohort_size": 1,
        "complete_months": 0,
        "cells": [cohort_cell(0, "partial", 1, 1), *NOT_OBSERVED_CELLS],
    },
]


def test_cohort_retention_golden_rows_have_states_and_null_unobserved_cells(client):
    dataset = upload(client, COHORT_ROWS)
    cohorts = get_customers(client, dataset, start="2026-01-10", end="2026-03-15").json()[
        "sections"
    ]["cohort_retention"]

    assert cohorts == {
        "availability": {"state": "available", "reason": None},
        "data_cutoff": "2026-03-15",
        "rows": GOLDEN_COHORTS,
    }
    later_start = get_customers(client, dataset, start="2026-01-15", end="2026-03-15").json()
    assert later_start["sections"]["cohort_retention"]["rows"] == GOLDEN_COHORTS
    february = get_customers(client, dataset, start="2026-02-01", end="2026-03-15").json()
    assert february["sections"]["cohort_retention"]["rows"] == [
        {**row, "cells": row["cells"][:2]} for row in GOLDEN_COHORTS[1:]
    ]
    full = get_customers(client, dataset, start="2026-01-10", end="2026-03-31").json()
    rows = full["sections"]["cohort_retention"]["rows"]
    assert rows[1]["cells"][1] == cohort_cell(1, "complete", 1, 0.5)
    assert rows[2]["cells"][0] == cohort_cell(0, "complete", 1, 1)
    assert [row["complete_months"] for row in rows] == [3, 2, 1]


def test_cohort_retention_rounds_retention_half_up_from_exact_counts(client):
    rows = [f"{c}1,2026-01-0{i + 1},p1,Mug,1,2.00,{c}" for i, c in enumerate("ABC")]
    dataset = upload(client, rows + ["a2,2026-02-01,p1,Mug,1,2.00,A"])
    cohorts = get_customers(client, dataset).json()["sections"]["cohort_retention"]

    assert cohorts["rows"][0]["cells"][1] == cohort_cell(1, "partial", 1, 0.3333)


def test_cohort_retention_is_current_range_only(client, monkeypatch):
    import app.api.customers as customers_api

    calls = []
    original = customers_api.read_cohort_retention

    def recording(connection, start, cutoff):
        calls.append((start.isoformat(), cutoff.isoformat()))
        return original(connection, start, cutoff)

    monkeypatch.setattr(customers_api, "read_cohort_retention", recording)
    dataset = upload(client, COHORT_ROWS)
    previous = get_customers(client, dataset, start="2026-03-01", end="2026-03-15").json()
    calls_previous = list(calls)
    calls.clear()
    yoy = get_customers(
        client, dataset, start="2026-03-01", end="2026-03-15", comparison="previous_year"
    ).json()

    assert previous["comparison"]["state"] == "available"
    assert calls_previous == [("2026-03-01", "2026-03-15")]
    assert calls == [("2026-03-01", "2026-03-15")]
    assert previous["sections"]["cohort_retention"] == yoy["sections"]["cohort_retention"]
    assert previous["sections"]["cohort_retention"]["rows"] == [
        {**GOLDEN_COHORTS[2], "cells": GOLDEN_COHORTS[2]["cells"][:1]}
    ]
    serialized = json.dumps(previous["sections"]["cohort_retention"])
    for field in ("comparison_value", "absolute_change", "percent_change", "change_status"):
        assert field not in serialized


def test_cohort_retention_without_overlapping_cohort_is_insufficient_data(client):
    dataset = upload(client, ["a1,2026-01-10,p1,Mug,1,2.00,A", "a2,2026-02-05,p1,Mug,1,2.00,A"])
    cohorts = get_customers(client, dataset, start="2026-02-01", end="2026-02-05").json()[
        "sections"
    ]["cohort_retention"]

    assert cohorts["availability"]["state"] == "insufficient_data"
    assert cohorts["availability"]["reason"]
    assert cohorts["data_cutoff"] == "2026-02-05"
    assert cohorts["rows"] == []


def test_cohort_retention_warning_tier_matches_normal_numbers(client):
    normal = upload(client, COHORT_ROWS[:-1])
    unidentified = [f"u{day},2026-02-{day},p1,Mug,1,2.00," for day in (11, 12, 13, 14)]
    warning = upload(client, COHORT_ROWS[:-1] + unidentified)
    params = {"start": "2026-01-10", "end": "2026-03-15"}
    normal_body = get_customers(client, normal, **params).json()
    warning_body = get_customers(client, warning, **params).json()

    assert normal_body["availability"]["tier"] == "normal"
    assert warning_body["availability"]["tier"] == "warning"
    assert (
        warning_body["sections"]["cohort_retention"] == normal_body["sections"]["cohort_retention"]
    )
    assert normal_body["sections"]["cohort_retention"]["rows"] == GOLDEN_COHORTS


def test_missing_and_suppressed_coverage_omit_identified_customer_section(client, monkeypatch):
    import app.api.customers as customers_api

    def not_run(*args):
        raise AssertionError("customer sections must not be queried")

    monkeypatch.setattr(customers_api, "read_new_vs_returning", not_run)
    monkeypatch.setattr(customers_api, "read_repeat_purchase", not_run)
    monkeypatch.setattr(customers_api, "read_days_between_purchases", not_run)
    monkeypatch.setattr(customers_api, "read_cohort_retention", not_run)
    missing = upload(client, ["o1,2025-01-01,p1,Mug,1,2.00"], REQUIRED)
    missing_body = get_customers(client, missing).json()
    assert missing_body["availability"]["tier"] == "missing"
    assert missing_body["availability"]["state"] == "unavailable"
    assert missing_body["sections"] == {}
    suppressed = upload(
        client,
        [
            "o1,2025-01-01,p1,Mug,1,2.00,C1",
            "o2,2025-01-02,p1,Mug,1,2.00,",
            "o3,2025-01-03,p1,Mug,1,2.00,",
        ],
    )
    suppressed_body = get_customers(client, suppressed).json()
    assert suppressed_body["availability"]["tier"] == "suppressed"
    assert suppressed_body["availability"]["state"] == "low_coverage"
    assert suppressed_body["sections"] == {}
    assert "repeat_purchase" not in suppressed_body["sections"]
    assert "days_between_purchases" not in missing_body["sections"]
    assert "days_between_purchases" not in suppressed_body["sections"]
    assert "cohort_retention" not in missing_body["sections"]
    assert "cohort_retention" not in suppressed_body["sections"]


def test_customers_default_and_comparison_are_shared_with_other_modules(client):
    dataset = upload(
        client,
        [
            "o1,2024-01-01,p1,Mug,1,2.00,CUST-1",
            "o2,2025-01-01,p1,Mug,1,3.00,CUST-2",
        ],
    )
    response = get_customers(client, dataset, comparison="previous_year")

    assert response.status_code == 200
    assert response.json()["comparison"] == {
        "mode": "previous_year",
        "current": {"start": "2024-01-01", "end": "2025-01-01"},
        "comparison": {"start": "2023-01-01", "end": "2024-01-01"},
        "state": "unavailable",
        "reason": "The comparison needs data from 2023-01-01, but the dataset starts on 2024-01-01.",
    }


@pytest.mark.parametrize(
    ("header", "rows", "tier", "state"),
    [
        (REQUIRED, ["o1,2025-01-01,p1,Mug,1,2.00"], "missing", "unavailable"),
        (
            CUSTOMER_HEADER,
            [
                "o1,2025-01-01,p1,Mug,1,2.00,CUST-1",
                "o2,2025-01-02,p1,Mug,1,2.00,",
                "o3,2025-01-03,p1,Mug,1,2.00,",
            ],
            "suppressed",
            "low_coverage",
        ),
        (
            CUSTOMER_HEADER,
            [
                "o1,2025-01-01,p1,Mug,1,2.00,CUST-1",
                "o2,2025-01-02,p1,Mug,1,2.00,CUST-2",
                "o3,2025-01-03,p1,Mug,1,2.00,",
            ],
            "warning",
            "available",
        ),
        (
            CUSTOMER_HEADER,
            [
                "o1,2025-01-01,p1,Mug,1,2.00,CUST-1",
                "o2,2025-01-02,p1,Mug,1,2.00,CUST-2",
                "o3,2025-01-03,p1,Mug,1,2.00,CUST-3",
            ],
            "normal",
            "available",
        ),
    ],
)
def test_customer_availability_tiers_are_200_states(client, header, rows, tier, state):
    dataset = upload(client, rows, header)
    response = get_customers(client, dataset)

    assert response.status_code == 200
    body = response.json()
    assert body["availability"]["tier"] == tier
    assert body["availability"]["state"] == state
    if tier in {"missing", "suppressed"}:
        assert body["sections"] == {}
    else:
        assert body["sections"]["identified_customers"]["value"]["value"] == (
            2 if tier == "warning" else 3
        )
        section = body["sections"]["new_vs_returning"]
        assert section["availability"] == {"state": "available", "reason": None}
        identified_sales = "4.0000" if tier == "warning" else "6.0000"
        assert section["new_customer_gross_sales"]["value"] == identified_sales
        assert section["returning_customer_gross_sales"]["value"] == "0.0000"
        assert section["identified_gross_sales"]["value"] == identified_sales
        repeat = body["sections"]["repeat_purchase"]
        assert repeat["active_customers"]["value"] == (2 if tier == "warning" else 3)
        assert repeat["repeat_customers"]["value"] == 0
        assert repeat["repeat_purchase_rate"]["value"] == 0
        assert repeat["availability"]["state"] == "zero_result"
    if tier in {"missing", "suppressed"}:
        assert "new_vs_returning" not in body["sections"]
        assert "repeat_purchase" not in body["sections"]


@pytest.mark.parametrize(
    "params",
    [
        {"start": "not-a-date"},
        {"start": "2025-01-03", "end": "2025-01-01"},
        {"start": "2024-01-01"},
    ],
)
def test_customers_uses_shared_invalid_range_errors(client, params):
    dataset = upload(client, ["o1,2025-01-01,p1,Mug,1,2.00,CUST-1"])
    response = get_customers(client, dataset, **params)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_range"


def test_customers_auth_and_method_rules(client):
    dataset = upload(client, ["o1,2025-01-01,p1,Mug,1,2.00,CUST-1"])
    path = f"/api/datasets/{dataset['dataset_id']}/customers"
    missing = client.get(path)
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    assert client.get(path, headers={"Authorization": "Basic wrong"}).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert (
        client.post(path, headers={"Authorization": f"Bearer {dataset['token']}"}).status_code
        == 405
    )
    assert (
        client.get(
            path + "/anything", headers={"Authorization": f"Bearer {dataset['token']}"}
        ).status_code
        == 404
    )


def test_customers_openapi_is_aggregate_only_and_route_is_unique(client):
    schema = client.get("/openapi.json").json()
    customer_schema = schema["paths"]["/api/datasets/{id}/customers"]["get"]["responses"]["200"][
        "content"
    ]["application/json"]["schema"]
    assert customer_schema["$ref"].endswith("CustomersResponse")
    serialized = json.dumps(schema["components"]["schemas"]["CustomersResponse"])
    assert "customer_id" not in serialized
    assert "customer_ids" not in serialized
    assert "NewVsReturningSection" in json.dumps(schema["components"]["schemas"])
    components = schema["components"]["schemas"]
    assert {"RepeatPurchaseSection", "ComparedRatio"} <= set(components)
    assert "repeat_purchase" in components["CustomerSections"]["properties"]
    assert "lifetime" not in json.dumps(components["RepeatPurchaseSection"])
    assert "lifetime" not in json.dumps(components["ComparedRatio"])
    assert {"DaysBetweenPurchasesSection", "DaysBetweenPurchasesBucket"} <= set(components)
    assert "days_between_purchases" in components["CustomerSections"]["properties"]
    assert {"CohortRetentionSection", "CohortRetentionRow", "CohortRetentionCell"} <= set(
        components
    )
    assert "cohort_retention" in components["CustomerSections"]["properties"]
    assert set(components["CohortRetentionSection"]["properties"]) == {
        "availability",
        "data_cutoff",
        "rows",
    }
    assert components["CohortRetentionCell"]["properties"]["state"]["enum"] == [
        "complete",
        "partial",
        "not_observed",
    ]
    assert set(components["DaysBetweenPurchasesSection"]["properties"]) == {
        "availability",
        "median_days",
        "interval_count",
        "contributing_customers",
        "buckets",
    }
    assert set(components["DaysBetweenPurchasesBucket"]["properties"]) == {
        "key",
        "min_days",
        "max_days",
        "interval_count",
        "share",
    }
    assert [path for path in schema["paths"] if "customer" in path] == [
        "/api/datasets/{id}/customers"
    ]
