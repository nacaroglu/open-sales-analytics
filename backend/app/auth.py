from dataclasses import dataclass
from datetime import UTC, datetime

import duckdb
from fastapi import Depends, Header

from app.config import Settings, get_settings
from app.errors import ApiError
from app.importer import dataset_path
from app.meta import read_meta
from app.schema import DatasetFileError, open_dataset_readonly
from app.tokens import is_valid_dataset_id, verify_token

_EXPIRY_SQL = "SELECT epoch(expires_at) FROM dataset_meta"


@dataclass(frozen=True)
class AuthorizedDataset:
    """What a route gets once the bearer token has been accepted."""

    id: str
    meta: dict


def get_now() -> datetime:
    """The current UTC time; tests override this dependency instead of sleeping."""
    return datetime.now(UTC)


def _unauthorized() -> ApiError:
    return ApiError(
        401,
        "unauthorized",
        "A valid bearer token is required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _not_found() -> ApiError:
    # One message for missing, malformed, expired and unreadable datasets.
    return ApiError(404, "not_found", "The dataset was not found.")


def _bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise _unauthorized()
    scheme, _, token = authorization.strip().partition(" ")
    token = token.strip()
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized()
    return token


def _read_unexpired_meta(settings: Settings, dataset_id: str, now: datetime) -> dict:
    """The dataset's metadata, or a 404 if it is missing, unreadable or expired."""
    try:
        connection = open_dataset_readonly(dataset_path(settings, dataset_id))
    except (FileNotFoundError, DatasetFileError, duckdb.Error):
        raise _not_found() from None
    try:
        row = connection.execute(_EXPIRY_SQL).fetchone()
        if row is None or row[0] is None or now.timestamp() >= row[0]:
            raise _not_found()
        return read_meta(connection)
    except (duckdb.Error, LookupError):
        raise _not_found() from None
    finally:
        connection.close()


def require_dataset(
    id: str,
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    now: datetime = Depends(get_now),
) -> AuthorizedDataset:
    """Dependency for routes with an ``{id}`` path parameter.

    Checks, in order: the header is a well-formed bearer header (401), the
    dataset exists, is readable and has not expired (404), the token matches
    (401). The token is read from the ``Authorization`` header only.
    """
    token = _bearer_token(authorization)
    if not is_valid_dataset_id(id):
        raise _not_found()
    meta = _read_unexpired_meta(settings, id, now)
    if not verify_token(id, token, settings):
        raise _unauthorized()
    return AuthorizedDataset(id=id, meta=meta)
