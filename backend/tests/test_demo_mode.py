import logging

import pytest
from app.config import Settings, get_settings
from app.main import app
from fastapi.testclient import TestClient

HEADER = "order_id,order_date,product_id,product_name,quantity,unit_price"
GOOD = HEADER + "\no1,2025-01-02,p1,Mug,2,19.99\no2,2025-03-04,p2,Cup,1,4.50\n"
MESSAGE = "Uploads are disabled on this demo. Upload your own file with the self-hosted version."
LOGGER = "app.api.datasets"


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


def make_client(settings):
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


@pytest.fixture
def demo_settings(data_dir):
    return Settings(PUBLIC_DEMO_MODE=True, DATASET_DIR=data_dir, MAX_UPLOAD_BYTES=1_000_000)


@pytest.fixture
def demo(demo_settings):
    yield make_client(demo_settings)
    app.dependency_overrides.clear()


@pytest.fixture
def normal(data_dir):
    yield make_client(Settings(DATASET_DIR=data_dir))
    app.dependency_overrides.clear()


def post_file(client, content=GOOD, currency="USD", **kwargs):
    data = {} if currency is None else {"currency": currency}
    return client.post(
        "/api/datasets", data=data, files={"file": ("x.csv", content, "text/csv")}, **kwargs
    )


def assert_403(response):
    assert response.status_code == 403
    assert response.json() == {"error": {"code": "upload_disabled", "message": MESSAGE}}
    assert "www-authenticate" not in response.headers


# --- the 403 ---


def test_valid_upload_is_refused_and_nothing_is_created(demo, data_dir):
    assert_403(post_file(demo))
    assert not data_dir.exists()


def test_nothing_is_added_to_an_existing_empty_dir(demo, data_dir):
    data_dir.mkdir()
    assert_403(post_file(demo))
    assert list(data_dir.iterdir()) == []


@pytest.mark.parametrize(
    "send",
    [
        lambda c: post_file(c, "not,a,valid\ncsv"),
        lambda c: c.post("/api/datasets", data={"currency": "USD"}),
        lambda c: post_file(c, currency="XXX"),
        lambda c: post_file(c, currency=None),
        lambda c: c.post("/api/datasets", content=b"hello", headers={"content-type": "text/plain"}),
        lambda c: c.post(
            "/api/datasets", content=b"{}", headers={"content-type": "application/json"}
        ),
        lambda c: c.post(
            "/api/datasets", content=b"garbage", headers={"content-type": "multipart/form-data"}
        ),
        lambda c: c.post("/api/datasets"),
        lambda c: post_file(c, "x" * 1_100_000),
    ],
    ids=[
        "invalid_csv",
        "no_file",
        "bad_currency",
        "no_currency",
        "not_multipart",
        "json",
        "multipart_without_boundary",
        "empty_body",
        "oversized",
    ],
)
def test_403_whatever_the_request_contains(demo, data_dir, send):
    assert_403(send(demo))
    assert not data_dir.exists()


def test_403_needs_no_token_and_ignores_one(demo):
    assert_403(post_file(demo, headers={"Authorization": "Bearer nonsense"}))


# --- the sample and other routes still work ---


def test_sample_works_in_demo_mode_with_normal_body_shape(demo, normal, data_dir):
    demo_response = demo.post("/api/datasets/sample")
    assert demo_response.status_code == 201
    app.dependency_overrides[get_settings] = lambda: Settings(DATASET_DIR=data_dir.parent / "n")
    normal_response = TestClient(app).post("/api/datasets/sample")
    assert normal_response.status_code == 201
    assert set(demo_response.json()) == set(normal_response.json())


def test_other_endpoints_behave_normally_in_demo_mode(demo, data_dir):
    created = demo.post("/api/datasets/sample").json()
    headers = {"Authorization": f"Bearer {created['token']}"}
    url = f"/api/datasets/{created['dataset_id']}"

    assert demo.get("/api/health").json() == {"status": "ok"}
    assert demo.get(url, headers=headers).json() == created["meta"]
    analytics = demo.get(url + "/analytics", headers=headers)
    assert analytics.status_code == 200
    assert analytics.json() == created["initial_summary"]
    assert demo.delete(url, headers=headers).status_code == 204
    assert demo.get(url, headers=headers).status_code == 404


# --- normal mode ---


def test_normal_mode_upload_still_works(normal, caplog):
    with caplog.at_level(logging.INFO, logger="app"):
        assert post_file(normal).status_code == 201
    assert [r for r in caplog.records if r.name.startswith("app")] == []


def test_normal_mode_sample_works_and_logs_nothing(normal, caplog):
    with caplog.at_level(logging.INFO, logger="app"):
        assert normal.post("/api/datasets/sample").status_code == 201
    assert [r for r in caplog.records if r.name.startswith("app")] == []


def test_normal_mode_bad_upload_is_still_a_client_error_and_logs_nothing(normal, caplog):
    with caplog.at_level(logging.INFO, logger="app"):
        assert post_file(normal, currency="XXX").status_code == 400
    assert [r for r in caplog.records if r.name.startswith("app")] == []


# --- logging ---


def test_each_rejection_logs_one_info_record_without_request_content(demo, caplog):
    body = (
        b'--B\r\nContent-Disposition: form-data; name="currency"\r\n\r\nMARKER_CURRENCY\r\n'
        b'--B\r\nContent-Disposition: form-data; name="file"; filename="MARKER_NAME.csv"\r\n'
        b"Content-Type: text/csv\r\n\r\nMARKER_BODY,x\r\n--B--\r\n"
    )
    with caplog.at_level(logging.DEBUG, logger="app"):
        response = demo.post(
            "/api/datasets",
            content=body,
            headers={
                "content-type": "multipart/form-data; boundary=B",
                "Authorization": "Bearer MARKER_AUTH",
                "X-Marker": "MARKER_HEADER",
            },
        )
    assert_403(response)

    records = [r for r in caplog.records if r.name.startswith("app")]
    assert len(records) == 1
    record = records[0]
    assert record.name == LOGGER
    assert record.levelno == logging.INFO
    text = record.getMessage() + " " + str(record.__dict__)
    assert "demo mode" in record.getMessage()
    assert "MARKER" not in text


def test_two_rejections_write_two_records(demo, caplog):
    with caplog.at_level(logging.INFO, logger="app"):
        post_file(demo)
        post_file(demo)
    assert len([r for r in caplog.records if r.name == LOGGER]) == 2
