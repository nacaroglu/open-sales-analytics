from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import duckdb
import pytest
from app.auth import get_now
from app.cleanup import sweep
from app.config import Settings, get_settings
from app.main import app
from app.response_cache import ResponseCache, get_response_cache
from app.schema import create_dataset
from app.tokens import new_dataset_id, new_token
from fastapi.testclient import TestClient

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def key(
    dataset="dataset",
    module="overview",
    start="2025-01-01",
    end="2025-01-02",
    mode="previous_period",
    options=(),
):
    return (dataset, module, start, end, mode, tuple(sorted(options)))


def test_cache_stores_bytes_and_expires_at_ttl_boundary():
    cache = ResponseCache(max_entries=4, ttl_seconds=5)
    cache.put(key(), b'{"x":1}', NOW, NOW + timedelta(days=1))

    assert cache.get(key(), NOW + timedelta(seconds=4)) == b'{"x":1}'
    assert cache.get(key(), NOW + timedelta(seconds=5)) is None


def test_cache_lifetime_is_capped_by_dataset_expiry():
    cache = ResponseCache(max_entries=4, ttl_seconds=300)
    cache.put(key(), b"body", NOW, NOW + timedelta(seconds=5))

    assert cache.get(key(), NOW + timedelta(seconds=4)) == b"body"
    assert cache.get(key(), NOW + timedelta(seconds=5)) is None


def test_cache_is_lru_and_bounded():
    cache = ResponseCache(max_entries=2, ttl_seconds=300)
    cache.put(key("a"), b"a", NOW, NOW + timedelta(days=1))
    cache.put(key("b"), b"b", NOW, NOW + timedelta(days=1))
    assert cache.get(key("a"), NOW) == b"a"
    cache.put(key("c"), b"c", NOW, NOW + timedelta(days=1))

    assert cache.get(key("b"), NOW) is None
    assert cache.get(key("a"), NOW) == b"a"
    assert cache.get(key("c"), NOW) == b"c"


def test_cache_can_be_disabled_and_invalidated():
    cache = ResponseCache(max_entries=0, ttl_seconds=300)
    cache.put(key(), b"body", NOW, NOW + timedelta(days=1))
    assert len(cache) == 0

    cache = ResponseCache(max_entries=4, ttl_seconds=300)
    cache.put(key("same"), b"a", NOW, NOW + timedelta(days=1))
    cache.put(key("other"), b"b", NOW, NOW + timedelta(days=1))
    cache.invalidate_dataset("same")
    assert cache.get(key("same"), NOW) is None
    assert cache.get(key("other"), NOW) == b"b"
    cache.clear()
    assert len(cache) == 0


def test_cache_never_exceeds_bound_under_concurrent_inserts():
    cache = ResponseCache(max_entries=10, ttl_seconds=300)

    def insert(index):
        cache.put(key(str(index)), str(index).encode(), NOW, NOW + timedelta(days=1))

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(insert, range(100)))

    assert len(cache) == 10


def test_sweep_invalidates_entries_for_deleted_datasets(tmp_path):
    settings = Settings(DATASET_DIR=tmp_path / "data")
    settings.dataset_dir.mkdir()
    dataset_id = new_dataset_id()
    path = settings.dataset_dir / f"{dataset_id}.duckdb"
    create_dataset(path)
    connection = duckdb.connect(str(path))
    connection.execute(
        "INSERT INTO dataset_meta (id, currency, created_at, expires_at, token_hash, row_count) VALUES (?, 'USD', ?, ?, 'hash', 1)",
        [dataset_id, NOW - timedelta(hours=2), NOW - timedelta(hours=1)],
    )
    connection.close()
    cache = ResponseCache(max_entries=4, ttl_seconds=300)
    cache.put((dataset_id, "overview"), b"body", NOW - timedelta(hours=2), NOW)

    assert sweep(settings, NOW, cache).datasets_removed == 1
    assert not any(key[0] == dataset_id for key in cache.keys())


def test_settings_expose_cache_limits(monkeypatch):
    monkeypatch.setenv("RESPONSE_CACHE_MAX_ENTRIES", "0")
    monkeypatch.setenv("RESPONSE_CACHE_TTL_SECONDS", "11")
    assert Settings().response_cache_max_entries == 0
    assert Settings().response_cache_ttl_seconds == 11


@pytest.fixture
def settings(tmp_path):
    return Settings(DATASET_DIR=tmp_path / "data", RESPONSE_CACHE_MAX_ENTRIES=20)


@pytest.fixture
def client(settings):
    cache = ResponseCache(max_entries=20, ttl_seconds=300)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_now] = lambda: NOW
    app.dependency_overrides[get_response_cache] = lambda: cache
    yield TestClient(app), cache
    app.dependency_overrides.clear()


def upload(client):
    response = client.post(
        "/api/datasets",
        data={"currency": "USD"},
        files={
            "file": (
                "x.csv",
                b"order_id,order_date,product_id,product_name,quantity,unit_price\n"
                b"o1,2025-01-01,p1,Mug,1,2.00\n",
                "text/csv",
            )
        },
    )
    assert response.status_code == 201
    return response.json()


def test_normalized_ranges_share_serialized_response_and_only_compute_once(client, monkeypatch):
    http, cache = client
    created = upload(http)
    import app.api.overview as overview

    calls = 0
    original = overview.build_overview

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(overview, "build_overview", counted)
    first = http.get(
        f"/api/datasets/{created['dataset_id']}/overview",
        headers={"Authorization": f"Bearer {created['token']}"},
    )
    second = http.get(
        f"/api/datasets/{created['dataset_id']}/overview",
        params={"start": "2025-01-01", "end": "2025-01-01"},
        headers={"Authorization": f"Bearer {created['token']}"},
    )

    assert first.status_code == second.status_code == 200
    assert first.content == second.content
    assert first.headers["Cache-Control"] == second.headers["Cache-Control"] == "no-store"
    assert calls == 1
    assert len(cache) == 1


def test_cache_keys_isolate_dataset_module_options_and_ranges(client):
    http, cache = client
    first = upload(http)
    second = upload(http)
    headers = {"Authorization": f"Bearer {first['token']}"}
    path = f"/api/datasets/{first['dataset_id']}/products/detail"

    for params in (
        {"product_id": "p1"},
        {"product_id": "p2"},
        {"product_id": "p1", "start": "2025-01-01", "end": "2025-01-01"},
        {"product_id": "p1", "comparison": "previous_year"},
    ):
        response = http.get(path, params=params, headers=headers)
        assert response.status_code in (200, 404)
    other = http.get(
        f"/api/datasets/{second['dataset_id']}/products",
        headers={"Authorization": f"Bearer {second['token']}"},
    )
    assert other.status_code == 200
    # The explicit min/max request above normalizes to the first request's key.
    assert len(cache) == 3


def test_errors_are_not_cached(client):
    http, cache = client
    created = upload(http)
    headers = {"Authorization": f"Bearer {created['token']}"}
    path = f"/api/datasets/{created['dataset_id']}/products/detail"
    for _ in range(2):
        response = http.get(path, params={"product_id": "missing"}, headers=headers)
        assert response.status_code == 404
    assert len(cache) == 0


def test_authorization_expiry_and_delete_do_not_use_a_cached_body(client):
    http, cache = client
    created = upload(http)
    path = f"/api/datasets/{created['dataset_id']}/products"
    good = {"Authorization": f"Bearer {created['token']}"}
    assert http.get(path, headers=good).status_code == 200
    assert len(cache) == 1
    assert http.get(path).status_code == 401
    assert http.get(path, headers={"Authorization": f"Bearer {new_token()}"}).status_code == 401

    app.dependency_overrides[get_now] = lambda: NOW + timedelta(days=2)
    assert http.get(path, headers=good).status_code == 404
    app.dependency_overrides[get_now] = lambda: NOW
    assert http.delete(f"/api/datasets/{created['dataset_id']}", headers=good).status_code == 204
    assert len(cache) == 0
    assert http.get(path, headers=good).status_code == 404
