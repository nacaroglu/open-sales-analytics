import hashlib
import hmac
import re
import secrets

import duckdb

from app.config import Settings, get_settings
from app.importer import dataset_path
from app.schema import DatasetFileError, open_dataset_readonly

_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{22}")


def new_dataset_id() -> str:
    """A random 22-character URL-safe dataset ID."""
    return secrets.token_urlsafe(16)


def new_token() -> str:
    """A random 43-character URL-safe bearer token, independent of the ID."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 of the token's UTF-8 bytes, as 64 lowercase hex characters."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_valid_dataset_id(value: str) -> bool:
    """True only for exactly 22 characters of the ID alphabet."""
    return isinstance(value, str) and _ID_PATTERN.fullmatch(value) is not None


def verify_token(dataset_id: str, presented_token: str, settings: Settings | None = None) -> bool:
    """Whether the token's hash matches the one stored for this dataset.

    Never raises for bad input or an unreadable dataset; any such case is False.
    Expiry is not checked here.
    """
    if not is_valid_dataset_id(dataset_id):
        return False
    try:
        presented_hash = hash_token(presented_token)
    except (UnicodeEncodeError, AttributeError):
        return False

    settings = settings or get_settings()
    try:
        connection = open_dataset_readonly(dataset_path(settings, dataset_id))
    except (FileNotFoundError, DatasetFileError, duckdb.Error):
        return False
    try:
        row = connection.execute("SELECT token_hash FROM dataset_meta").fetchone()
    except duckdb.Error:
        return False
    finally:
        connection.close()

    if row is None or not isinstance(row[0], str):
        return False
    return hmac.compare_digest(presented_hash.encode("utf-8"), row[0].encode("utf-8"))
