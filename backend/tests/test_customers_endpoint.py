import json
import re
from datetime import UTC, datetime

import pytest
from app.analytics.shared.metrics import METRICS, RFM_NOTE
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
            "o5,2025-01-05,p1,Mug,1,6.00,CUSTMARKER-0003",
            "o6,2025-01-05,p1,Mug,1,7.00,CUSTMARKER-0004",
            "o7,2025-01-05,p1,Mug,1,8.00,CUSTMARKER-0005",
            "o8,2025-01-06,p1,Mug,1,9.00,",
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
            "reason": "Only 6 of 8 orders (75%) have a customer_id; customer results describe those orders only.",
        },
    }
    assert body["coverage"] == {
        "dataset": {
            "tier": "warning",
            "coverage": 0.75,
            "identified_orders": 6,
            "unidentified_orders": 2,
            "total_orders": 8,
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
    value = body["sections"]["historical_customer_value"]
    assert value["availability"] == {"state": "available", "reason": None}
    assert (value["customer_count"], value["average"], value["median"]) == (
        2,
        "2.5000",
        "2.5000",
    )
    assert value["rows"][0]["cells"] == [
        {"month_offset": 0, "state": "partial", "value_per_customer": "2.5000"}
    ]
    assert body["sections"]["rfm"]["availability"]["state"] == "insufficient_data"
    with_rfm = get_customers(client, dataset, start="2025-01-01", end="2025-01-06")
    rfm = with_rfm.json()["sections"]["rfm"]
    assert rfm["availability"] == {"state": "available", "reason": None}
    assert rfm["customer_count"] == 5
    assert set(rfm) == {"availability", "customer_count", "recency_anchor", "note", "segments"}
    for segment in rfm["segments"]:
        assert set(segment) == {"segment", "customer_count", "share"}
    drilldown = with_rfm.json()["sections"]["rfm_drilldown"]
    assert drilldown["availability"] == {"state": "available", "reason": None}
    assert (drilldown["customer_count"], drilldown["gross_sales"]) == (5, "31.0000")
    assert len(drilldown["segments"]) == 6
    for segment in drilldown["segments"]:
        assert set(segment) == {
            "segment",
            "customer_count",
            "gross_sales",
            "gross_sales_share",
            "recency_distribution",
            "frequency_distribution",
        }
    markers = tuple(f"CUSTMARKER-000{index}" for index in range(1, 6))
    for body_text in (response.text, with_interval.text, with_rfm.text):
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


VALUE_ROWS = [
    "a1,2026-01-10,p1,Mug,1,100.00,A",
    "a2,2026-02-05,p1,Mug,1,30.00,A",
    "f1,2026-01-20,p1,Mug,1,50.00,F",
    "b1,2026-02-05,p1,Mug,1,20.00,B",
    "b2,2026-03-10,p1,Mug,1,40.00,B",
    "u1,2026-02-15,p1,Mug,1,999.00,",
    "u2,2026-03-31,p1,Mug,1,1.00,",
]


def value_cell(offset, state, value):
    return {"month_offset": offset, "state": state, "value_per_customer": value}


GOLDEN_VALUE = {
    "availability": {"state": "available", "reason": None},
    "data_cutoff": "2026-03-31",
    "customer_count": 3,
    "average": "80.0000",
    "median": "60.0000",
    "rows": [
        {
            "cohort_month": "2026-01",
            "cohort_size": 2,
            "cells": [
                value_cell(0, "complete", "75.0000"),
                value_cell(1, "complete", "90.0000"),
                value_cell(2, "complete", "90.0000"),
            ],
        },
        {
            "cohort_month": "2026-02",
            "cohort_size": 1,
            "cells": [
                value_cell(0, "complete", "20.0000"),
                value_cell(1, "complete", "60.0000"),
                value_cell(2, "not_observed", None),
            ],
        },
    ],
    "all_cohorts": [
        {"month_offset": 0, "value_per_customer": "56.6667", "contributing_cohorts": 2},
        {"month_offset": 1, "value_per_customer": "80.0000", "contributing_cohorts": 2},
        {"month_offset": 2, "value_per_customer": "90.0000", "contributing_cohorts": 1},
    ],
}


def test_historical_customer_value_golden_section_matches_cohort_rows(client):
    dataset = upload(client, VALUE_ROWS)
    sections = get_customers(client, dataset, start="2026-01-10", end="2026-03-31").json()[
        "sections"
    ]
    value = sections["historical_customer_value"]

    assert value == GOLDEN_VALUE
    retention = sections["cohort_retention"]
    assert [
        (row["cohort_month"], row["cohort_size"], [c["state"] for c in row["cells"]])
        for row in value["rows"]
    ] == [
        (row["cohort_month"], row["cohort_size"], [c["state"] for c in row["cells"]])
        for row in retention["rows"]
    ]
    assert value["data_cutoff"] == retention["data_cutoff"]


def test_historical_customer_value_is_current_range_only(client, monkeypatch):
    import app.api.customers as customers_api

    calls = []
    original = customers_api.read_historical_customer_value

    def recording(connection, start, cutoff):
        calls.append((start.isoformat(), cutoff.isoformat()))
        return original(connection, start, cutoff)

    monkeypatch.setattr(customers_api, "read_historical_customer_value", recording)
    dataset = upload(client, VALUE_ROWS)
    params = {"start": "2026-02-20", "end": "2026-03-31"}
    previous = get_customers(client, dataset, **params).json()
    calls_previous = list(calls)
    calls.clear()
    yoy = get_customers(client, dataset, comparison="previous_year", **params).json()

    assert previous["comparison"]["state"] == "available"
    assert calls_previous == [("2026-02-20", "2026-03-31")]
    assert calls == [("2026-02-20", "2026-03-31")]
    section = previous["sections"]["historical_customer_value"]
    assert section == yoy["sections"]["historical_customer_value"]
    assert (section["customer_count"], section["average"], section["median"]) == (
        1,
        "60.0000",
        "60.0000",
    )
    serialized = json.dumps(section)
    for field in ("comparison_value", "absolute_change", "percent_change", "change_status"):
        assert field not in serialized


def test_historical_customer_value_warning_tier_matches_normal_numbers(client):
    normal = upload(client, [row for row in VALUE_ROWS if not row.endswith(",")])
    warning = upload(client, VALUE_ROWS)
    params = {"start": "2026-01-10", "end": "2026-03-10"}
    normal_body = get_customers(client, normal, **params).json()
    warning_body = get_customers(client, warning, **params).json()

    assert normal_body["availability"]["tier"] == "normal"
    assert warning_body["availability"]["tier"] == "warning"
    assert (
        warning_body["sections"]["historical_customer_value"]
        == normal_body["sections"]["historical_customer_value"]
    )
    assert normal_body["sections"]["historical_customer_value"]["average"] == "80.0000"


def test_historical_customer_value_without_cohort_is_insufficient_data(client):
    dataset = upload(client, ["a1,2026-01-10,p1,Mug,1,2.00,A", "a2,2026-02-05,p1,Mug,1,2.00,A"])
    value = get_customers(client, dataset, start="2026-02-01", end="2026-02-05").json()["sections"][
        "historical_customer_value"
    ]

    assert value["availability"]["state"] == "insufficient_data"
    assert value["availability"]["reason"]
    assert value["data_cutoff"] == "2026-02-05"
    assert (value["customer_count"], value["average"], value["median"]) == (0, None, None)
    assert value["rows"] == []
    assert value["all_cohorts"] == []


RFM_ROWS = [
    "p1,2026-03-27,p1,Mug,1,100.00,P",
    "p2,2026-03-28,p1,Mug,1,100.00,P",
    "p3,2026-03-29,p1,Mug,1,100.00,P",
    "p4,2026-03-30,p1,Mug,1,100.00,P",
    "p5,2026-03-31,p1,Mug,1,100.00,P",
    "q1,2026-03-19,p1,Mug,1,100.00,Q",
    "q2,2026-03-20,p1,Mug,1,100.00,Q",
    "q3,2026-03-21,p1,Mug,1,100.00,Q",
    "r1,2026-02-28,p1,Mug,1,150.00,R",
    "r2,2026-03-01,p1,Mug,1,150.00,R",
    "s1,2026-01-30,p1,Mug,1,50.00,S",
    "t1,2025-12-31,p1,Mug,1,20.00,T",
]

GOLDEN_RFM_SEGMENTS = [
    {"segment": "Champions", "customer_count": 2, "share": 0.4},
    {"segment": "Loyal", "customer_count": 1, "share": 0.2},
    {"segment": "Potential Loyalists", "customer_count": 0, "share": 0},
    {"segment": "Needs Attention", "customer_count": 0, "share": 0},
    {"segment": "At Risk", "customer_count": 0, "share": 0},
    {"segment": "Lost", "customer_count": 2, "share": 0.4},
]


def test_rfm_golden_section_uses_all_activity_through_the_range_end(client):
    dataset = upload(client, RFM_ROWS)
    rfm = get_customers(client, dataset, start="2026-03-31", end="2026-03-31").json()["sections"][
        "rfm"
    ]

    assert rfm == {
        "availability": {"state": "available", "reason": None},
        "customer_count": 5,
        "recency_anchor": "2026-03-31",
        "note": RFM_NOTE,
        "segments": GOLDEN_RFM_SEGMENTS,
    }


def test_rfm_does_not_depend_on_the_request_clock(client, settings):
    upload_time = datetime(2026, 4, 1, 12, tzinfo=UTC)
    app.dependency_overrides[get_now] = lambda: upload_time
    dataset = upload(client, RFM_ROWS)
    sections = []
    for now in (upload_time, datetime(2026, 4, 2, 6, tzinfo=UTC)):
        app.dependency_overrides[get_now] = lambda now=now: now
        app.dependency_overrides[get_response_cache] = lambda: ResponseCache(
            max_entries=20, ttl_seconds=300
        )
        response = get_customers(client, dataset, start="2026-03-01", end="2026-03-31")
        assert response.status_code == 200
        sections.append(response.json()["sections"]["rfm"])

    assert sections[0] == sections[1]
    assert sections[0]["segments"] == GOLDEN_RFM_SEGMENTS


def test_rfm_is_byte_identical_and_ignores_the_comparison_mode(client):
    dataset = upload(client, RFM_ROWS)
    texts = []
    for comparison in ("previous_period", "previous_period", "previous_year"):
        app.dependency_overrides[get_response_cache] = lambda: ResponseCache(
            max_entries=20, ttl_seconds=300
        )
        body = get_customers(
            client, dataset, start="2026-03-01", end="2026-03-31", comparison=comparison
        ).json()
        texts.append(json.dumps(body["sections"]["rfm"]))

    assert texts[0] == texts[1] == texts[2]
    for field in ("comparison_value", "absolute_change", "percent_change", "change_status"):
        assert field not in texts[0]


def test_rfm_warning_tier_matches_normal_numbers(client):
    normal = upload(client, RFM_ROWS)
    unidentified = [f"u{day},2026-03-{day},p1,Mug,1,999.00," for day in (10, 11, 12, 13)]
    warning = upload(client, RFM_ROWS + unidentified)
    params = {"start": "2026-03-01", "end": "2026-03-31"}
    normal_body = get_customers(client, normal, **params).json()
    warning_body = get_customers(client, warning, **params).json()

    assert normal_body["availability"]["tier"] == "normal"
    assert warning_body["availability"]["tier"] == "warning"
    assert warning_body["sections"]["rfm"] == normal_body["sections"]["rfm"]
    assert normal_body["sections"]["rfm"]["segments"] == GOLDEN_RFM_SEGMENTS


def test_rfm_with_four_customers_is_insufficient_data(client):
    dataset = upload(client, [row for row in RFM_ROWS if not row.startswith("t1")])
    rfm = get_customers(client, dataset, start="2026-01-30", end="2026-03-31").json()["sections"][
        "rfm"
    ]

    assert rfm["availability"] == {
        "state": "insufficient_data",
        "reason": "RFM needs at least 5 identified customers.",
    }
    assert (rfm["customer_count"], rfm["segments"]) == (4, [])
    assert rfm["note"]


def test_rfm_drilldown_golden_section_through_the_endpoint(client):
    dataset = upload(client, RFM_ROWS)
    body = get_customers(client, dataset, start="2026-03-31", end="2026-03-31").json()
    drilldown = body["sections"]["rfm_drilldown"]

    assert list(body["sections"])[-4:] == [
        "rfm",
        "rfm_drilldown",
        "purchase_frequency",
        "concentration",
    ]
    assert drilldown["availability"] == {"state": "available", "reason": None}
    assert (drilldown["customer_count"], drilldown["recency_anchor"]) == (5, "2026-03-31")
    assert drilldown["customer_count"] == body["sections"]["rfm"]["customer_count"]
    assert drilldown["gross_sales"] == "1170.0000"
    assert [
        (s["segment"], s["customer_count"], s["gross_sales"], s["gross_sales_share"])
        for s in drilldown["segments"]
    ] == [
        ("Champions", 2, "800.0000", 0.6838),
        ("Loyal", 1, "300.0000", 0.2564),
        ("Potential Loyalists", 0, "0.0000", 0),
        ("Needs Attention", 0, "0.0000", 0),
        ("At Risk", 0, "0.0000", 0),
        ("Lost", 2, "70.0000", 0.0598),
    ]


def test_rfm_drilldown_is_byte_identical_and_ignores_the_comparison_mode(client):
    dataset = upload(client, RFM_ROWS)
    texts = []
    for comparison in ("previous_period", "previous_period", "previous_year"):
        app.dependency_overrides[get_response_cache] = lambda: ResponseCache(
            max_entries=20, ttl_seconds=300
        )
        body = get_customers(
            client, dataset, start="2026-03-01", end="2026-03-31", comparison=comparison
        ).json()
        texts.append(json.dumps(body["sections"]["rfm_drilldown"]))

    assert texts[0] == texts[1] == texts[2]
    for field in ("comparison_value", "absolute_change", "percent_change", "change_status"):
        assert field not in texts[0]


def test_rfm_drilldown_warning_tier_matches_normal_numbers(client):
    normal = upload(client, RFM_ROWS)
    unidentified = [f"u{day},2026-03-{day},p1,Mug,1,999.00," for day in (10, 11, 12, 13)]
    warning = upload(client, RFM_ROWS + unidentified)
    params = {"start": "2026-03-01", "end": "2026-03-31"}
    normal_body = get_customers(client, normal, **params).json()
    warning_body = get_customers(client, warning, **params).json()

    assert normal_body["availability"]["tier"] == "normal"
    assert warning_body["availability"]["tier"] == "warning"
    assert warning_body["sections"]["rfm_drilldown"] == normal_body["sections"]["rfm_drilldown"]
    assert normal_body["sections"]["rfm_drilldown"]["gross_sales"] == "1170.0000"


def test_rfm_drilldown_with_four_customers_is_insufficient_data(client):
    dataset = upload(client, [row for row in RFM_ROWS if not row.startswith("t1")])
    drilldown = get_customers(client, dataset, start="2026-01-30", end="2026-03-31").json()[
        "sections"
    ]["rfm_drilldown"]

    assert drilldown == {
        "availability": {
            "state": "insufficient_data",
            "reason": "RFM needs at least 5 identified customers.",
        },
        "customer_count": 4,
        "recency_anchor": "2026-03-31",
        "gross_sales": "1150.0000",
        "segments": [],
    }


def test_missing_and_suppressed_coverage_omit_identified_customer_section(client, monkeypatch):
    import app.api.customers as customers_api

    def not_run(*args):
        raise AssertionError("customer sections must not be queried")

    monkeypatch.setattr(customers_api, "read_new_vs_returning", not_run)
    monkeypatch.setattr(customers_api, "read_repeat_purchase", not_run)
    monkeypatch.setattr(customers_api, "read_days_between_purchases", not_run)
    monkeypatch.setattr(customers_api, "read_cohort_retention", not_run)
    monkeypatch.setattr(customers_api, "read_historical_customer_value", not_run)
    monkeypatch.setattr(customers_api, "read_rfm", not_run)
    monkeypatch.setattr(customers_api, "read_rfm_drilldown", not_run)
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
    assert "historical_customer_value" not in missing_body["sections"]
    assert "historical_customer_value" not in suppressed_body["sections"]
    assert "rfm" not in missing_body["sections"]
    assert "rfm" not in suppressed_body["sections"]
    assert "rfm_drilldown" not in missing_body["sections"]
    assert "rfm_drilldown" not in suppressed_body["sections"]


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
    value_models = {
        "HistoricalCustomerValueSection",
        "HistoricalCustomerValueRow",
        "HistoricalCustomerValueCell",
        "HistoricalCustomerValueCurvePoint",
    }
    assert value_models <= set(components)
    assert "historical_customer_value" in components["CustomerSections"]["properties"]
    assert set(components["HistoricalCustomerValueSection"]["properties"]) == {
        "availability",
        "data_cutoff",
        "customer_count",
        "average",
        "median",
        "rows",
        "all_cohorts",
    }
    for name in value_models - {"HistoricalCustomerValueSection"}:
        assert all(prop.get("description") for prop in components[name]["properties"].values()), (
            name
        )
    section_props = components["HistoricalCustomerValueSection"]["properties"]
    assert all(
        prop.get("description") for key, prop in section_props.items() if key != "availability"
    )
    assert components["HistoricalCustomerValueCell"]["properties"]["state"]["enum"] == [
        "complete",
        "partial",
        "not_observed",
    ]
    banned = ("lifetime", "ltv", "clv")
    referenced = _referenced_components(components, "CustomersResponse")
    for name in referenced:
        component = components[name]
        texts = [component.get("description", "")]
        for key, prop in component.get("properties", {}).items():
            texts += [key, prop.get("description", "")]
        lowered = " ".join(texts).lower()
        assert not any(word in lowered for word in banned), name
    for key, metric in METRICS.items():
        assert not any(word in key.lower() or word in metric.label.lower() for word in banned)
    assert METRICS["historical_customer_value"].label == "Historical Customer Value"
    value_fields = set()
    for name in value_models:
        value_fields |= set(components[name]["properties"])
    assert not any("projected" in field or "predicted" in field for field in value_fields)
    assert {"RfmSection", "RfmSegment"} <= set(components)
    assert "rfm" in components["CustomerSections"]["properties"]
    assert set(components["RfmSection"]["properties"]) == {
        "availability",
        "customer_count",
        "recency_anchor",
        "note",
        "segments",
    }
    assert set(components["RfmSegment"]["properties"]) == {"segment", "customer_count", "share"}
    for name in ("RfmSection", "RfmSegment"):
        assert all(
            prop.get("description")
            for key, prop in components[name]["properties"].items()
            if key != "availability"
        ), name
    rfm_text = json.dumps([components["RfmSection"], components["RfmSegment"]]).lower()
    assert "customer_id" not in rfm_text
    assert '"r"' not in rfm_text and "score" not in json.dumps(
        list(components["RfmSegment"]["properties"])
    )
    drilldown_models = (
        "RfmDrilldownSection",
        "RfmDrilldownSegment",
        "RfmRecencyBucket",
        "RfmFrequencyBucket",
    )
    assert set(drilldown_models) <= set(components)
    assert components["CustomerSections"]["properties"]["rfm_drilldown"]["anyOf"][0][
        "$ref"
    ].endswith("RfmDrilldownSection")
    assert set(components["RfmDrilldownSection"]["properties"]) == {
        "availability",
        "customer_count",
        "recency_anchor",
        "gross_sales",
        "segments",
    }
    assert set(components["RfmDrilldownSegment"]["properties"]) == {
        "segment",
        "customer_count",
        "gross_sales",
        "gross_sales_share",
        "recency_distribution",
        "frequency_distribution",
    }
    assert set(components["RfmRecencyBucket"]["properties"]) == {
        "key",
        "min_days",
        "max_days",
        "customer_count",
    }
    assert set(components["RfmFrequencyBucket"]["properties"]) == {
        "key",
        "min_orders",
        "max_orders",
        "customer_count",
    }
    for name in drilldown_models:
        assert all(
            prop.get("description")
            for key, prop in components[name]["properties"].items()
            if key != "availability"
        ), name
    drilldown_text = json.dumps([components[name] for name in drilldown_models]).lower()
    assert "customer_id" not in drilldown_text
    assert "score" not in json.dumps(
        [list(components[name]["properties"]) for name in drilldown_models]
    )
    assert [path for path in schema["paths"] if "customer" in path] == [
        "/api/datasets/{id}/customers"
    ]


def _referenced_components(components, root):
    """Names of the component schemas reachable from ``root`` through ``$ref``."""
    seen, pending = set(), [root]
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        text = json.dumps(components[name])
        pending += [ref.rsplit("/", 1)[-1] for ref in _REF.findall(text)]
    return seen


_REF = re.compile(r'"\$ref": "([^"]+)"')
