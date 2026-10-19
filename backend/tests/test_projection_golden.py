import csv
import io
import json
from datetime import UTC, datetime

import pytest
from app.auth import get_now
from app.config import Settings, get_settings
from app.main import app
from app.response_cache import ResponseCache, get_response_cache
from fastapi.testclient import TestClient

HEADER = "order_id,order_date,product_id,product_name,quantity,unit_price,customer_id"
SIX_COLUMN_HEADER = "order_id,order_date,product_id,product_name,quantity,unit_price"
END = "2025-12-31"
MID_MONTH_END = "2025-12-15"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def client(tmp_path):
    settings = Settings(DATASET_DIR=tmp_path / "data", DATASET_TTL_HOURS=24)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_now] = lambda: NOW
    app.dependency_overrides[get_response_cache] = lambda: ResponseCache(
        max_entries=100, ttl_seconds=300
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


def _rows(
    *,
    earliest_day: int = 16,
    customer_variant: bool = False,
    coverage_variant: bool = False,
    mature_variant: bool = False,
) -> list[list[str]]:
    """Build the 1,000-order golden population.

    The five mature cohorts each contain 80 customers. Each customer starts at
    10.00; 30 customers per mature cohort receive a 1.00 sale at cohort age 3.
    The October 2025 cohort has 50 customers, sales at ages 0 and 2 (November
    is deliberately zero), and the December cohort has 50 customers at age 0.
    That gives 500 identified customers and 700 identified orders after the
    300 unidentified orders are added.
    """
    mature_months = ["2024-06", "2024-07", "2024-08", "2024-09", "2024-10"]
    assignments: list[tuple[str, str]] = []
    for month in mature_months:
        assignments.extend(
            (f"CUST-{index:04d}", month) for index in range(len(assignments), len(assignments) + 80)
        )
    assignments.extend((f"CUST-{index:04d}", "2025-10") for index in range(400, 450))
    assignments.extend((f"CUST-{index:04d}", "2025-12") for index in range(450, 500))

    if mature_variant:
        assignments = [
            (customer_id, "2025-10") if cohort == "2024-06" else (customer_id, cohort)
            for customer_id, cohort in assignments
        ]

    rows: list[list[str]] = []
    for index, (customer_id, cohort) in enumerate(assignments):
        if cohort == "2024-06":
            order_date = f"2024-06-{earliest_day:02d}"
        else:
            order_date = f"{cohort}-01"
        effective_customer = (
            "CUST-0498" if customer_variant and customer_id == "CUST-0499" else customer_id
        )
        rows.append(
            [
                f"FIRST-{index:04d}",
                order_date,
                "P1",
                "Golden Product",
                "1",
                "10.00",
                effective_customer,
            ]
        )

    repeat_index = 0
    repeat_dates = ["2024-09-01", "2024-10-01", "2024-11-01", "2024-12-01", "2025-01-01"]
    for month_index, _month in enumerate(mature_months):
        start = month_index * 80
        for customer_index in range(start, start + 30):
            customer_id = assignments[customer_index][0]
            rows.append(
                [
                    f"MATURE-REPEAT-{repeat_index:04d}",
                    repeat_dates[month_index],
                    "P1",
                    "Golden Product",
                    "1",
                    "1.00",
                    customer_id,
                ]
            )
            repeat_index += 1

    for customer_index in range(400, 450):
        customer_id = assignments[customer_index][0]
        rows.append(
            [
                f"IMMATURE-REPEAT-{customer_index:04d}",
                "2025-12-15",
                "P1",
                "Golden Product",
                "1",
                "3.00",
                customer_id,
            ]
        )

    if mature_variant:
        for customer_index in range(30):
            customer_id = assignments[customer_index][0]
            rows.append(
                [
                    f"MATURE-VARIANT-REPEAT-{customer_index:04d}",
                    "2025-12-15",
                    "P1",
                    "Golden Product",
                    "1",
                    "1.00",
                    customer_id,
                ]
            )
        rows = [
            row
            for row in rows
            if not row[0].startswith("MATURE-REPEAT-") or int(row[0].rsplit("-", 1)[1]) >= 30
        ]

    if coverage_variant:
        for row in rows:
            if row[0].startswith("IMMATURE-REPEAT-"):
                row[-1] = ""
                break

    for index in range(299):
        rows.append([f"UNKNOWN-{index:04d}", "2025-12-15", "P1", "Golden Product", "1", "5.00", ""])
    rows.append(["UNKNOWN-0299", "2025-12-31", "P1", "Golden Product", "1", "5.00", ""])
    assert len(rows) == 1000
    return rows


def _csv(rows: list[list[str]], header: str = HEADER) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(header.split(","))
    writer.writerows(rows if header == HEADER else [row[:6] for row in rows])
    return output.getvalue().encode("utf-8")


def upload(client, rows, *, header=HEADER):
    response = client.post(
        "/api/datasets",
        files={"file": ("projection-golden.csv", _csv(rows, header), "text/csv")},
        data={"currency": "USD"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def customers(client, dataset, **params):
    return client.get(
        f"/api/datasets/{dataset['dataset_id']}/customers",
        params=params,
        headers={"Authorization": f"Bearer {dataset['token']}"},
    )


def projection_body(client, dataset, **params):
    response = customers(client, dataset, **params)
    assert response.status_code == 200, response.text
    return response.json()["projected_12_month_customer_value"]


def test_eligible_golden_dataset_matches_hand_worked_projection(client, capsys):
    dataset = upload(client, _rows())
    projection = projection_body(client, dataset, end=END)

    # Arithmetic table (all amounts are USD per customer):
    # mature cohorts: observed 10.00 + (30 * 1.00 / 80) at age 3 = 10.375;
    # October cohort: observed 10.00 + 0.00 + 3.00 = 13.00, then 0.375 estimate;
    # December cohort: observed 10.00, then 0.375 estimate;
    # headline observed=(400*10.375+50*13+50*10)/500=10.6000;
    # headline projected=(50*0.375+50*0.375)/500=0.0750.
    assert projection["eligibility"]["status"] == "eligible"
    assert projection["eligibility"]["conditions"] == [
        {
            "code": "history_months",
            "label": "At least 18 months of order history",
            "actual": 18,
            "threshold": 18,
            "passed": True,
        },
        {
            "code": "identified_customers",
            "label": "At least 500 identified customers",
            "actual": 500,
            "threshold": 500,
            "passed": True,
        },
        {
            "code": "customer_coverage",
            "label": "Customer coverage of at least 70%",
            "actual": "0.7000",
            "threshold": "0.7000",
            "passed": True,
        },
        {
            "code": "mature_cohorts",
            "label": "At least 5 monthly cohorts with 12 months of observed behaviour",
            "actual": 5,
            "threshold": 5,
            "passed": True,
        },
    ]
    assert projection["value"]["customers"] == 500
    assert projection["value"]["contributing_mature_cohorts"] == 5
    assert projection["value"]["observed_per_customer"] == "10.6000"
    assert projection["value"]["projected_per_customer_estimate"] == "0.0750"
    assert projection["value"]["total_per_customer_estimate"] == "10.6750"
    assert [
        (
            row["cohort_month"],
            row["observed_per_customer"],
            row["projected_per_customer_estimate"],
            row["total_per_customer_estimate"],
        )
        for row in projection["value"]["cohorts"]
    ] == [
        ("2024-06", "10.3750", "0.0000", "10.3750"),
        ("2024-07", "10.3750", "0.0000", "10.3750"),
        ("2024-08", "10.3750", "0.0000", "10.3750"),
        ("2024-09", "10.3750", "0.0000", "10.3750"),
        ("2024-10", "10.3750", "0.0000", "10.3750"),
        ("2025-10", "13.0000", "0.3750", "13.3750"),
        ("2025-12", "10.0000", "0.3750", "10.3750"),
    ]
    assert "CUST-0499" not in json.dumps(projection)
    assert "CUST-0499" not in capsys.readouterr().out


@pytest.mark.parametrize(
    ("name", "kwargs", "failed_code"),
    [
        ("history", {"earliest_day": 17}, "history_months"),
        ("customers", {"customer_variant": True}, "identified_customers"),
        ("coverage", {"coverage_variant": True}, "customer_coverage"),
        ("mature cohorts", {"mature_variant": True}, "mature_cohorts"),
    ],
)
def test_each_ineligible_variant_fails_only_one_condition(client, name, kwargs, failed_code):
    dataset = upload(client, _rows(**kwargs))
    end = MID_MONTH_END if name == "history" else END
    projection = projection_body(client, dataset, end=end)
    conditions = projection["eligibility"]["conditions"]

    assert projection["eligibility"]["status"] == "ineligible"
    assert [condition["code"] for condition in conditions if not condition["passed"]] == [
        failed_code
    ]
    assert all(
        condition["passed"] is (condition["code"] != failed_code) for condition in conditions
    )
    assert projection["value"] is None
    if failed_code == "customer_coverage":
        assert (
            next(condition for condition in conditions if condition["code"] == failed_code)[
                "actual"
            ]
            == "0.6990"
        )


def test_partial_cohorts_and_mid_month_cutoff_are_handled_without_filling_zero_sales(client):
    dataset = upload(client, _rows())
    full = projection_body(client, dataset, end=END)
    mid_month = projection_body(client, dataset, end=MID_MONTH_END)
    assert mid_month["value"] == full["value"]
    assert mid_month["data_cutoff"] == MID_MONTH_END
    october = next(row for row in full["value"]["cohorts"] if row["cohort_month"] == "2025-10")
    december = next(row for row in full["value"]["cohorts"] if row["cohort_month"] == "2025-12")
    assert october["observed_age_months"] == 3
    assert october["observed_per_customer"] == "13.0000"
    assert october["projected_per_customer_estimate"] == "0.3750"
    assert december["observed_age_months"] == 1
    assert december["projected_per_customer_estimate"] == "0.3750"


def test_six_column_and_low_coverage_datasets_have_no_projection_value(client):
    six_column = upload(client, _rows(), header=SIX_COLUMN_HEADER)
    unavailable = projection_body(client, six_column, end=END)
    assert unavailable["eligibility"]["status"] == "unavailable"
    assert unavailable["value"] is None

    low_coverage_rows = _rows()
    for row in low_coverage_rows[:251]:
        row[-1] = ""
    low_coverage = upload(client, low_coverage_rows)
    suppressed = projection_body(client, low_coverage, end=END)
    assert suppressed["eligibility"]["status"] == "ineligible"
    assert suppressed["value"] is None
    assert (
        next(
            condition
            for condition in suppressed["eligibility"]["conditions"]
            if condition["code"] == "customer_coverage"
        )["passed"]
        is False
    )


def test_projection_is_reproducible_and_start_date_does_not_change_it(client):
    rows = _rows()
    first = upload(client, rows)
    second = upload(client, rows)
    first_block = projection_body(client, first, start="2025-01-01", end=END)
    second_block = projection_body(client, second, start="2025-10-01", end=END)
    assert first_block == second_block


def test_bundled_sample_projection_contract_is_checked_against_literals(client):
    created = client.post("/api/datasets/sample")
    assert created.status_code == 201
    dataset = created.json()
    projection = projection_body(client, dataset, end=END)
    assert projection["eligibility"]["status"] == "eligible"
    assert projection["value"]["contributing_mature_cohorts"] == 13
    assert projection["value"]["observed_per_customer"] == "281.9098"
    assert projection["value"]["projected_per_customer_estimate"] == "56.1233"
