import os
import re
import stat

import app.ingest as ingest_module
import duckdb
import pytest
from app.config import Settings, get_settings
from app.errors import ApiError, error_body
from app.main import app
from app.meta import read_meta
from app.schema import open_dataset_readonly
from app.tokens import hash_token, verify_token
from fastapi.testclient import TestClient

HEADER = "order_id,order_date,product_id,product_name,quantity,unit_price"
GOOD_ROWS = ["o1,2025-01-02,p1,Mug,2,19.99", "o2,2025-03-04,p2,Cup,1,4.50"]


def csv_text(*rows, header=HEADER):
    return header + "\n" + "\n".join(rows) + "\n"


GOOD = csv_text(*GOOD_ROWS)


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "data"


@pytest.fixture
def settings(data_dir):
    return Settings(DATASET_DIR=data_dir, MAX_UPLOAD_BYTES=10_000, MAX_ROWS=1000)


@pytest.fixture
def client(settings):
    app.dependency_overrides[get_settings] = lambda: settings
    yield TestClient(app)
    app.dependency_overrides.clear()


def upload(client, content=GOOD, currency="USD", filename="data.csv", content_type="text/csv"):
    data = {} if currency is None else {"currency": currency}
    files = {"file": (filename, content, content_type)}
    return client.post("/api/datasets", data=data, files=files)


def tree(root):
    return sorted(str(p.relative_to(root)) for p in root.rglob("*")) if root.exists() else []


def assert_clean(data_dir):
    """Nothing but an empty uploads/ folder may remain."""
    assert set(tree(data_dir)) <= {"uploads"}
    uploads = data_dir / "uploads"
    assert not uploads.exists() or not any(uploads.iterdir())


def error_of(response):
    body = response.json()
    assert list(body) == ["error"]
    return body["error"]


# --- success ---


def test_valid_file_creates_a_dataset(client, settings, data_dir):
    response = upload(client)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"dataset_id", "token", "meta", "warnings", "initial_summary"}
    assert body["warnings"] == []
    meta = body["meta"]
    assert set(meta) == {"id", "currency", "created_at", "expires_at", "row_count", "date_range"}
    assert meta["id"] == body["dataset_id"]
    assert meta["currency"] == "USD"
    assert meta["row_count"] == 2
    assert meta["date_range"] == {"min": "2025-01-02", "max": "2025-03-04"}
    assert (data_dir / f"{body['dataset_id']}.duckdb").is_file()
    assert verify_token(body["dataset_id"], body["token"], settings)
    assert set(tree(data_dir)) == {"uploads", f"{body['dataset_id']}.duckdb"}
    assert not any((data_dir / "uploads").iterdir())


def test_timestamps_are_utc_to_the_second(client):
    meta = upload(client).json()["meta"]

    pattern = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ"
    assert re.fullmatch(pattern, meta["created_at"])
    assert re.fullmatch(pattern, meta["expires_at"])
    assert meta["expires_at"] > meta["created_at"]


def test_response_has_no_token_hash_or_path(client, data_dir):
    response = upload(client)

    text = response.text
    token = response.json()["token"]
    assert hash_token(token) not in text
    assert "token_hash" not in text
    assert str(data_dir) not in text
    assert ".duckdb" not in text
    assert response.headers["cache-control"] == "no-store"


def test_two_uploads_make_two_datasets(client, data_dir):
    first = upload(client).json()
    second = upload(client).json()

    assert first["dataset_id"] != second["dataset_id"]
    assert first["token"] != second["token"]
    assert len(list(data_dir.glob("*.duckdb"))) == 2


def test_warnings_from_structure_and_rows_are_both_returned(client):
    content = csv_text("o1,2025-01-02,p1,Mug,2,0", header=HEADER + ",note,memo")
    content = content.replace("Mug,2,0", "Mug,2,0,a,b")

    body = upload(client, content).json()

    codes = [(w["code"], w["field"]) for w in body["warnings"]]
    assert codes == [
        ("extra_column", "note"),
        ("extra_column", "memo"),
        ("zero_price", "unit_price"),
    ]
    assert set(body["warnings"][0]) == {"code", "reason", "row_number", "field"}


def test_dataset_file_and_folders_are_private(client, data_dir):
    dataset_id = upload(client).json()["dataset_id"]

    assert stat.S_IMODE((data_dir / f"{dataset_id}.duckdb").stat().st_mode) == 0o600
    assert stat.S_IMODE(data_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((data_dir / "uploads").stat().st_mode) == 0o700


def test_filename_is_never_used_in_a_path(client, data_dir, tmp_path):
    response = upload(client, filename="../../x.csv")

    assert response.status_code == 201
    assert sorted(p.name for p in tmp_path.iterdir()) == ["data"]
    assert not (tmp_path / "x.csv").exists()
    assert not (data_dir / "x.csv").exists()


# --- validation failures ---


def test_row_errors_return_the_422_envelope(client, data_dir):
    content = csv_text("o1,2025-01-02,p1,Mug,0,19.99", "o2,not-a-date,p2,Cup,1,4.5")

    response = upload(client, content)

    assert response.status_code == 422
    error = error_of(response)
    assert set(error) == {"code", "message", "errors", "error_count", "warnings"}
    assert error["code"] == "validation_failed"
    assert error["error_count"] == 2
    assert [(e["code"], e["row_number"], e["field"]) for e in error["errors"]] == [
        ("invalid_quantity", 2, "quantity"),
        ("invalid_date", 3, "order_date"),
    ]
    assert_clean(data_dir)


def test_cross_row_errors_are_returned(client):
    content = csv_text("o1,2025-01-02,p1,Mug,1,1", "o1,2025-01-02,p1,Mug,1,1")

    error = error_of(upload(client, content))

    assert [e["code"] for e in error["errors"]] == ["duplicate_line"]


def test_errors_are_capped_but_error_count_is_true(client, settings):
    rows = [f"o{i},2025-01-02,p{i},Item,0,1" for i in range(150)]

    error = error_of(upload(client, csv_text(*rows)))

    assert len(error["errors"]) == 100
    assert error["error_count"] == 150


def test_structure_errors_stop_further_checks(client, monkeypatch):
    calls = []
    monkeypatch.setattr(ingest_module, "stage_csv", lambda *a: calls.append("stage"))
    monkeypatch.setattr(ingest_module, "validate_rows", lambda *a: calls.append("rows"))
    content = csv_text(
        "o1,2025-01-02,p1,Mug,0", header="order_id,order_date,product_id,product_name,quantity"
    )

    response = upload(client, content)

    assert response.status_code == 422
    assert [e["code"] for e in error_of(response)["errors"]] == ["missing_column"]
    assert calls == []


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (HEADER + "\n", "no_data_rows"),
        ("", "empty_file"),
        (
            csv_text(
                "o1,2025-01-02,p1,Mug,1",
                header="order_id,order_date,product_id,product_name,quantity",
            ),
            "missing_column",
        ),
    ],
)
def test_broken_files_return_422_not_500(client, data_dir, content, code):
    response = upload(client, content)

    assert response.status_code == 422
    assert error_of(response)["errors"][0]["code"] == code
    assert_clean(data_dir)


def test_structure_warnings_are_kept_in_a_422(client):
    content = csv_text("o1,2025-01-02,p1,Mug,0,1,x", header=HEADER + ",note")

    error = error_of(upload(client, content))

    assert [w["code"] for w in error["warnings"]] == ["extra_column"]


def test_png_named_csv_is_a_422(client, data_dir):
    png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + bytes(range(256)) * 4

    response = upload(client, png, filename="data.csv", content_type="text/csv")

    assert response.status_code == 422
    assert_clean(data_dir)


def test_oversized_file_is_refused_and_reading_stops(client, settings, data_dir, monkeypatch):
    sizes = []
    real = ingest_module.validate_structure

    def spy(path, *args):
        sizes.append(os.path.getsize(path))
        return real(path, *args)

    monkeypatch.setattr(ingest_module, "validate_structure", spy)
    content = csv_text(*["o1,2025-01-02,p1,Mug,1,1"] * 2000)
    assert len(content) > settings.max_upload_bytes * 2

    response = upload(client, content)

    assert response.status_code == 422
    assert error_of(response)["errors"][0]["code"] == "file_too_large"
    assert sizes == [settings.max_upload_bytes + 1]
    assert_clean(data_dir)


# --- bad requests ---


@pytest.mark.parametrize("currency", ["usd", "XYZ", "", " USD", "USD ", "US"])
def test_bad_currency_is_400_before_any_file_is_written(client, data_dir, currency):
    response = upload(client, currency=currency)

    assert response.status_code == 400
    assert error_of(response)["code"] == "invalid_request"
    assert not data_dir.exists()


def test_missing_currency_is_400(client, data_dir):
    response = upload(client, currency=None)

    assert response.status_code == 400
    assert error_of(response)["code"] == "invalid_request"
    assert_clean(data_dir)


def test_currency_after_the_file_is_still_checked_and_cleaned_up(client, data_dir):
    boundary = "b0undary"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.csv"\r\n\r\n{GOOD}\r\n'
        f'--{boundary}\r\nContent-Disposition: form-data; name="currency"\r\n\r\nnope\r\n--{boundary}--\r\n'
    )

    response = client.post(
        "/api/datasets",
        content=body,
        headers={"content-type": f"multipart/form-data; boundary={boundary}"},
    )

    assert response.status_code == 400
    assert_clean(data_dir)


def test_every_supported_currency_is_accepted(client):
    for currency in ["USD", "EUR", "GBP", "TRY", "CAD", "AUD", "JPY", "CHF", "SEK", "PLN"]:
        assert upload(client, currency=currency).json()["meta"]["currency"] == currency


def test_no_file_part_is_400(client, data_dir):
    response = client.post(
        "/api/datasets", data={"currency": "USD"}, files={"other": ("a.csv", GOOD)}
    )

    assert response.status_code == 400
    assert error_of(response)["code"] == "invalid_request"
    assert_clean(data_dir)


def test_two_file_parts_are_400(client, data_dir):
    response = client.post(
        "/api/datasets",
        data={"currency": "USD"},
        files=[("file", ("a.csv", GOOD)), ("file", ("b.csv", GOOD))],
    )

    assert response.status_code == 400
    assert_clean(data_dir)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"json": {"currency": "USD"}},
        {"content": GOOD, "headers": {"content-type": "text/csv"}},
        {"data": {"currency": "USD"}},  # urlencoded form
        {"content": b"", "headers": {}},
        {"content": "--x\r\ngarbage", "headers": {"content-type": "multipart/form-data"}},
        {
            "content": "--x\r\ngarbage",
            "headers": {"content-type": "multipart/form-data; boundary=x"},
        },
    ],
)
def test_non_multipart_request_is_400_in_our_shape(client, data_dir, kwargs):
    response = client.post("/api/datasets", **kwargs)

    assert response.status_code == 400
    assert error_of(response)["code"] == "invalid_request"
    assert "detail" not in response.json()
    assert_clean(data_dir)


def test_get_on_the_route_uses_the_error_shape(client):
    response = client.get("/api/datasets")

    assert response.status_code == 405
    assert error_of(response)["code"] == "method_not_allowed"


# --- failures and cleanup ---


def test_unexpected_failure_is_500_and_leaves_nothing(client, data_dir, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError(f"secret path {data_dir}")

    monkeypatch.setattr(ingest_module, "import_dataset", boom)

    response = upload(client)

    assert response.status_code == 500
    assert error_of(response) == {
        "code": "internal_error",
        "message": "Something went wrong on the server.",
    }
    assert "secret" not in response.text and str(data_dir) not in response.text
    assert "Traceback" not in response.text
    assert_clean(data_dir)


def test_failure_after_import_removes_the_dataset_file(client, data_dir, monkeypatch):
    def boom(connection):
        raise RuntimeError("no meta")

    monkeypatch.setattr(ingest_module, "read_meta", boom)

    response = upload(client)

    assert response.status_code == 500
    assert not list(data_dir.glob("*.duckdb*"))
    assert_clean(data_dir)


def test_staging_connection_is_closed_after_a_422_and_a_500(client, monkeypatch):
    opened = []
    real = ingest_module.stage_csv

    def spy(path):
        connection = real(path)
        opened.append(connection)
        return connection

    monkeypatch.setattr(ingest_module, "stage_csv", spy)
    upload(client, csv_text("o1,2025-01-02,p1,Mug,0,1"))
    monkeypatch.setattr(ingest_module, "import_dataset", lambda *a, **k: 1 / 0)
    upload(client)

    assert len(opened) == 2
    for connection in opened:
        with pytest.raises(duckdb.ConnectionException):
            connection.execute("SELECT 1")


def test_no_staging_directory_survives(client, data_dir):
    upload(client)
    upload(client, csv_text("o1,bad,p1,Mug,1,1"))

    assert not [p for p in data_dir.rglob("*") if p.name.startswith(".staging-")]


# --- shared modules ---


def test_read_meta_reads_a_dataset_file(client, settings):
    dataset_id = upload(client).json()["dataset_id"]

    connection = open_dataset_readonly(settings.dataset_dir / f"{dataset_id}.duckdb")
    try:
        meta = read_meta(connection)
    finally:
        connection.close()

    assert meta["id"] == dataset_id
    assert meta["row_count"] == 2
    assert "token_hash" not in meta


def test_read_meta_without_a_row_raises_lookup_error():
    connection = duckdb.connect(":memory:")
    from app.schema import DATASET_META_DDL, LINE_ITEMS_DDL

    connection.execute(LINE_ITEMS_DDL)
    connection.execute(DATASET_META_DDL)

    with pytest.raises(LookupError):
        read_meta(connection)


def test_ingest_csv_rejects_an_unknown_currency_and_deletes_the_file(settings, tmp_path):
    path = tmp_path / "in.csv"
    path.write_text(GOOD)

    with pytest.raises(ValueError):
        ingest_module.ingest_csv(path, "XXX", settings)

    assert not path.exists()


def test_api_error_uses_the_shared_body_and_headers():
    from app.errors import register_error_handlers
    from fastapi import FastAPI

    small = FastAPI()
    register_error_handlers(small)

    @small.get("/x")
    def x():
        raise ApiError(429, "slow_down", "Try later.", headers={"Retry-After": "5"})

    response = TestClient(small).get("/x")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "5"
    assert response.json() == error_body("slow_down", "Try later.")
