import re
from datetime import UTC, datetime

import app.tokens as tokens
import pytest
from app.config import Settings
from app.importer import dataset_path, import_dataset
from app.tokens import hash_token, is_valid_dataset_id, new_dataset_id, new_token, verify_token
from app.validation import stage_csv

HEADER = "order_id,order_date,product_id,product_name,quantity,unit_price"
NOW = datetime(2025, 6, 1, 12, 30, tzinfo=UTC)


@pytest.fixture
def settings(tmp_path):
    return Settings(DATASET_DIR=tmp_path / "data")


def make_dataset(settings, tmp_path, token, dataset_id=None):
    dataset_id = dataset_id or new_dataset_id()
    csv_path = tmp_path / f"{dataset_id}.csv"
    csv_path.write_text(HEADER + "\no1,2025-01-02,p1,Mug,2,19.99\n", encoding="utf-8")
    import_dataset(
        stage_csv(csv_path), csv_path, dataset_id, "USD", hash_token(token), settings, NOW
    )
    return dataset_id


def test_dataset_id_shape():
    value = new_dataset_id()
    assert re.fullmatch(r"[A-Za-z0-9_-]{22}", value)
    assert is_valid_dataset_id(value)


def test_token_shape():
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}", new_token())


def test_ids_and_tokens_are_unique():
    assert len({new_dataset_id() for _ in range(1000)}) == 1000
    assert len({new_token() for _ in range(1000)}) == 1000


def test_id_and_token_are_generated_independently(monkeypatch):
    calls = []
    real = tokens.secrets.token_urlsafe

    def spy(n):
        calls.append(n)
        return real(n)

    monkeypatch.setattr(tokens.secrets, "token_urlsafe", spy)
    new_dataset_id()
    new_token()
    assert calls == [16, 32]
    assert new_dataset_id()[:22] != new_token()[:22]


def test_hash_token_is_sha256_hex_of_utf8():
    assert hash_token("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    digest = hash_token("é")
    assert re.fullmatch(r"[0-9a-f]{64}", digest)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "short",
        "a" * 21,
        "a" * 23,
        "../../etc/passwd",
        "a" * 21 + "/",
        "a" * 21 + ".",
        "a" * 21 + "\n",
        "a" * 21 + "é",
        " " + "a" * 21,
    ],
)
def test_is_valid_dataset_id_rejects(value):
    assert not is_valid_dataset_id(value)


def test_is_valid_dataset_id_accepts_full_alphabet():
    assert is_valid_dataset_id("Az09-_" * 3 + "Az09")


def test_verify_accepts_the_right_token(settings, tmp_path):
    token = new_token()
    dataset_id = make_dataset(settings, tmp_path, token)
    assert verify_token(dataset_id, token, settings) is True


def test_verify_defaults_to_get_settings(settings, tmp_path, monkeypatch):
    token = new_token()
    dataset_id = make_dataset(settings, tmp_path, token)
    monkeypatch.setattr(tokens, "get_settings", lambda: settings)
    assert verify_token(dataset_id, token) is True


def test_verify_rejects_wrong_empty_and_hash_as_token(settings, tmp_path):
    token = new_token()
    dataset_id = make_dataset(settings, tmp_path, token)
    assert verify_token(dataset_id, new_token(), settings) is False
    assert verify_token(dataset_id, "", settings) is False
    assert verify_token(dataset_id, hash_token(token), settings) is False


def test_verify_rejects_token_of_another_dataset(settings, tmp_path):
    first, second = new_token(), new_token()
    first_id = make_dataset(settings, tmp_path, first)
    second_id = make_dataset(settings, tmp_path, second)
    assert verify_token(first_id, first, settings) is True
    assert verify_token(first_id, second, settings) is False
    assert verify_token(second_id, first, settings) is False


def test_verify_false_when_no_dataset_file(settings):
    assert verify_token(new_dataset_id(), new_token(), settings) is False


def test_verify_false_when_file_is_not_a_duckdb_file(settings):
    dataset_id = new_dataset_id()
    settings.dataset_dir.mkdir(parents=True)
    dataset_path(settings, dataset_id).write_text("this is not a database", encoding="utf-8")
    assert verify_token(dataset_id, new_token(), settings) is False


def test_verify_false_when_dataset_meta_is_missing_or_empty(settings):
    import duckdb

    settings.dataset_dir.mkdir(parents=True)
    no_table, no_row = new_dataset_id(), new_dataset_id()
    duckdb.connect(str(dataset_path(settings, no_table))).close()
    from app.schema import create_dataset

    create_dataset(dataset_path(settings, no_row))
    assert verify_token(no_table, new_token(), settings) is False
    assert verify_token(no_row, new_token(), settings) is False


@pytest.mark.parametrize("token", ["tökén", "日本語", "\ud800", "a" * 42 + "é"])
def test_verify_false_for_non_ascii_token(settings, tmp_path, token):
    dataset_id = make_dataset(settings, tmp_path, new_token())
    assert verify_token(dataset_id, token, settings) is False


def test_verify_non_ascii_token_can_match_its_own_hash(settings, tmp_path):
    dataset_id = make_dataset(settings, tmp_path, "tökén")
    assert verify_token(dataset_id, "tökén", settings) is True


@pytest.mark.parametrize(
    "bad_id", ["../../etc/passwd", "", "a/b", "a" * 21, "a" * 23, "a" * 21 + "/"]
)
def test_verify_never_opens_a_file_for_a_malformed_id(settings, monkeypatch, bad_id):
    def fail(path):
        pytest.fail("open_dataset_readonly must not be called")

    monkeypatch.setattr(tokens, "open_dataset_readonly", fail)
    assert verify_token(bad_id, new_token(), settings) is False


def test_verify_closes_the_connection(settings, tmp_path, monkeypatch):
    opened = []
    real = tokens.open_dataset_readonly

    def spy(path):
        connection = real(path)
        opened.append(connection)
        return connection

    monkeypatch.setattr(tokens, "open_dataset_readonly", spy)
    token = new_token()
    dataset_id = make_dataset(settings, tmp_path, token)
    good = verify_token(dataset_id, token, settings)
    dataset_path(settings, dataset_id).unlink()

    assert good is True
    import duckdb

    for connection in opened:
        with pytest.raises(duckdb.ConnectionException):
            connection.execute("SELECT 1")


def test_verify_closes_the_connection_when_query_fails(settings, monkeypatch):
    import duckdb

    opened = []
    real = tokens.open_dataset_readonly

    def spy(path):
        connection = real(path)
        opened.append(connection)
        return connection

    monkeypatch.setattr(tokens, "open_dataset_readonly", spy)
    settings.dataset_dir.mkdir(parents=True)
    dataset_id = new_dataset_id()
    duckdb.connect(str(dataset_path(settings, dataset_id))).close()
    assert verify_token(dataset_id, new_token(), settings) is False
    with pytest.raises(duckdb.ConnectionException):
        opened[0].execute("SELECT 1")


def test_module_does_not_log_or_print():
    source = open(tokens.__file__, encoding="utf-8").read()
    assert "print(" not in source and "logging" not in source and "logger" not in source
