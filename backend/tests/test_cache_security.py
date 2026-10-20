from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from itertools import cycle, islice

import pytest
from app import auth
from app.auth import get_now
from app.cleanup import sweep
from app.config import Settings, get_settings
from app.main import app
from app.response_cache import ResponseCache, get_response_cache
from app.tokens import hash_token, new_token
from fastapi.testclient import TestClient

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
HEADER = "order_id,order_date,product_id,product_name,quantity,unit_price,customer_id"
ROWS = "\n".join(
    [
        "o1,2025-01-01,p1,Mug,1,2.00,CUST-PRIVATE-001",
        "o2,2025-01-02,p1,Mug,1,3.00,CUST-PRIVATE-001",
        "o3,2025-01-03,p2,Pen,2,4.00,CUST-PRIVATE-002",
        "o4,2025-01-04,p2,Pen,1,5.00,",
    ]
)

MODULES = (
    ("overview", "/overview", {}),
    ("products", "/products", {}),
    ("product_detail", "/products/detail", {"product_id": "p1"}),
    ("customers", "/customers", {}),
    ("projection", "/customers", {}),
)


@pytest.fixture
def settings(tmp_path):
    return Settings(DATASET_DIR=tmp_path / "data", RESPONSE_CACHE_MAX_ENTRIES=8)


@pytest.fixture
def client(settings):
    cache = ResponseCache(max_entries=8, ttl_seconds=300)
    clock = {"now": NOW}
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_now] = lambda: clock["now"]
    app.dependency_overrides[get_response_cache] = lambda: cache
    with TestClient(app) as http:
        yield http, cache, clock
    app.dependency_overrides.clear()


def upload(http, price="2.00"):
    rows = ROWS.replace("2.00", price, 1)
    response = http.post(
        "/api/datasets",
        files={"file": ("cache.csv", f"{HEADER}\n{rows}\n".encode(), "text/csv")},
        data={"currency": "USD"},
    )
    assert response.status_code == 201
    return response.json()


def request(http, dataset, path, params=None, token=None):
    headers = {} if token is None else {"Authorization": f"Bearer {token}"}
    return http.get(
        f"/api/datasets/{dataset['dataset_id']}{path}", headers=headers, params=params or {}
    )


@pytest.mark.parametrize("_,path,params", MODULES)
def test_every_module_rechecks_authorization_on_a_cache_hit(client, _, path, params):
    http, cache, _ = client
    first = upload(http)
    second = upload(http, price="20.00")
    good = request(http, first, path, params, first["token"])
    assert good.status_code == 200
    assert len(cache) >= 1

    for bad in (
        None,
        new_token(),
        second["token"],
    ):
        response = request(http, first, path, params, bad)
        assert response.status_code == 401
        assert "gross_sales" not in response.text
        assert "CUST-PRIVATE-001" not in response.text
    for malformed in ("Bearer", "Basic abc"):
        response = http.get(
            f"/api/datasets/{first['dataset_id']}{path}",
            params=params,
            headers={"Authorization": malformed},
        )
        assert response.status_code == 401


@pytest.mark.parametrize("_,path,params", MODULES)
def test_authentication_runs_on_both_cache_misses_and_hits(client, _, path, params, monkeypatch):
    http, _, _ = client
    dataset = upload(http)
    calls = 0
    original = auth.verify_token

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(auth, "verify_token", counted)
    assert request(http, dataset, path, params, dataset["token"]).status_code == 200
    assert request(http, dataset, path, params, dataset["token"]).status_code == 200
    assert calls == 2


@pytest.mark.parametrize("_,path,params", MODULES)
def test_identical_options_are_isolated_between_datasets(client, _, path, params):
    http, cache, _ = client
    first = upload(http, price="2.00")
    second = upload(http, price="20.00")
    first_body = request(http, first, path, params, first["token"])
    second_body = request(http, second, path, params, second["token"])
    assert first_body.status_code == second_body.status_code == 200
    assert first_body.content != second_body.content

    cache.clear()
    second_first = request(http, second, path, params, second["token"])
    first_second = request(http, first, path, params, first["token"])
    assert second_first.content == second_body.content
    assert first_second.content == first_body.content


def test_same_bytes_have_separate_tokens_and_cache_entries(client):
    http, cache, _ = client
    first = upload(http)
    second = upload(http)
    assert first["dataset_id"] != second["dataset_id"]
    assert first["token"] != second["token"]
    path = "/overview"
    assert request(http, first, path, token=first["token"]).status_code == 200
    assert request(http, second, path, token=second["token"]).status_code == 200
    assert len(cache) == 2
    keys = cache.keys()
    assert {key[0] for key in keys} == {first["dataset_id"], second["dataset_id"]}
    assert all(first["token"] not in repr(key) for key in keys)
    assert all(hash_token(first["token"]) not in repr(key) for key in keys)


def test_every_cache_key_option_is_a_miss_and_errors_are_not_cached(client):
    http, cache, _ = client
    dataset = upload(http)
    good = {"Authorization": f"Bearer {dataset['token']}"}
    base = f"/api/datasets/{dataset['dataset_id']}"
    requests = [
        ("/overview", {"start": "2025-01-01", "end": "2025-01-03"}),
        ("/overview", {"start": "2025-01-01", "end": "2025-01-04"}),
        ("/overview", {"comparison": "previous_year"}),
        ("/products", {"dormancy_days": "30"}),
        ("/products", {"dormancy_days": "90"}),
        ("/products/detail", {"product_id": "p1"}),
        ("/products/detail", {"product_id": "p2"}),
        ("/customers", {"start": "2025-01-01", "end": "2025-01-03"}),
    ]
    for path, params in requests:
        assert http.get(base + path, params=params, headers=good).status_code == 200
    assert len(cache) == len(requests)
    invalid = http.get(
        base + "/overview", params={"start": "2025-01-04", "end": "2025-01-01"}, headers=good
    )
    assert invalid.status_code == 400
    before = len(cache)
    assert http.get(base + "/overview", headers=good).status_code == 200
    assert len(cache) <= 8
    assert http.get(base + "/overview", headers={"Authorization": "Bearer bad"}).status_code == 401
    assert len(cache) == before


def test_cached_response_is_served_before_expiry_and_never_after_it(client):
    http, cache, clock = client
    dataset = upload(http)
    expiry = datetime.fromisoformat(dataset["meta"]["expires_at"].replace("Z", "+00:00"))
    path = "/overview"
    assert request(http, dataset, path, token=dataset["token"]).status_code == 200
    clock["now"] = expiry - timedelta(seconds=1)
    assert request(http, dataset, path, token=dataset["token"]).status_code == 200
    assert len(cache) == 1
    clock["now"] = expiry
    assert request(http, dataset, path, token=dataset["token"]).status_code == 404
    assert cache.get(next(iter(cache.keys())), expiry) is None
    assert len(cache) == 0


def test_sweep_and_delete_remove_only_their_dataset_cache_entries(client):
    http, cache, clock = client
    first = upload(http)
    clock["now"] = NOW + timedelta(hours=1)
    second = upload(http, price="20.00")
    clock["now"] = NOW + timedelta(hours=24, minutes=30)
    assert request(http, first, "/overview", token=first["token"]).status_code == 404
    assert request(http, second, "/overview", token=second["token"]).status_code == 200
    cache.clear()
    clock["now"] = NOW
    assert request(http, first, "/overview", token=first["token"]).status_code == 200
    assert request(http, second, "/overview", token=second["token"]).status_code == 200
    clock["now"] = NOW + timedelta(hours=24, minutes=30)
    settings = app.dependency_overrides[get_settings]()
    result = sweep(settings, clock["now"], cache)
    assert result.datasets_removed == 1
    assert all(key[0] != first["dataset_id"] for key in cache.keys())
    assert any(key[0] == second["dataset_id"] for key in cache.keys())
    clock["now"] = NOW + timedelta(hours=1)
    assert (
        http.delete(
            f"/api/datasets/{second['dataset_id']}",
            headers={"Authorization": f"Bearer {second['token']}"},
        ).status_code
        == 204
    )
    assert all(key[0] != second["dataset_id"] for key in cache.keys())
    assert request(http, second, "/overview", token=second["token"]).status_code == 404


def test_a_new_client_starts_with_an_empty_cache(client):
    http, cache, _ = client
    dataset = upload(http)
    assert request(http, dataset, "/overview", token=dataset["token"]).status_code == 200
    assert len(cache) == 1
    settings = app.dependency_overrides[get_settings]()
    fresh_cache = ResponseCache(max_entries=8, ttl_seconds=300)
    app.dependency_overrides[get_response_cache] = lambda: fresh_cache
    with TestClient(app) as restarted:
        assert len(fresh_cache) == 0
        assert request(restarted, dataset, "/overview", token=dataset["token"]).status_code == 200
    app.dependency_overrides[get_response_cache] = lambda: cache
    assert settings.dataset_dir.exists()
    assert len(fresh_cache) == 1


def test_cache_bound_and_concurrent_requests_never_return_another_dataset(client, capsys):
    http, cache, _ = client
    datasets = [upload(http, price=price) for price in ("2.00", "20.00", "200.00")]
    specs = []
    for dataset in datasets:
        for path, params in (
            ("/overview", {}),
            ("/overview", {"comparison": "previous_year"}),
            ("/products", {"dormancy_days": "30"}),
            ("/products", {"dormancy_days": "90"}),
            ("/customers", {}),
        ):
            response = request(http, dataset, path, params, dataset["token"])
            assert response.status_code == 200
            specs.append((dataset, path, params, response.content))
    cache.clear()

    def run(spec):
        dataset, path, params, expected = spec
        response = request(http, dataset, path, params, dataset["token"])
        return response.status_code, response.content == expected

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(run, islice(cycle(specs), 200)))
    assert all(status == 200 and matches for status, matches in results)
    assert len(cache) <= 8
    captured = capsys.readouterr()
    output = captured.err + captured.out
    for dataset in datasets:
        assert dataset["token"] not in output
        assert hash_token(dataset["token"]) not in output
    assert "CUST-PRIVATE-001" not in output
