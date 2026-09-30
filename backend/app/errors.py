from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def error_body(code: str, message: str, **details: Any) -> dict:
    """The one error body every endpoint returns: ``{"error": {"code", "message", ...}}``.

    ``details`` are extra keys placed inside ``error`` (for example ``errors``).
    """
    return {"error": {"code": code, "message": message, **details}}


class ApiError(Exception):
    """Raise from a route to answer with ``error_body`` and this status."""

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        headers: dict[str, str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.headers = headers
        self.details = details or {}


_STATUS_CODES = {404: "not_found", 405: "method_not_allowed"}


def _respond(status: int, body: dict, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(body, status_code=status, headers=headers)


async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
    return _respond(exc.status, error_body(exc.code, exc.message, **exc.details), exc.headers)


async def _request_invalid(_: Request, __: RequestValidationError) -> JSONResponse:
    # Never echo FastAPI's detail list: it can quote request values.
    return _respond(400, error_body("invalid_request", "The request is not valid."))


async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _STATUS_CODES.get(exc.status_code, "http_error")
    return _respond(exc.status_code, error_body(code, "The request could not be served."), exc.headers)


async def _unexpected(_: Request, __: Exception) -> JSONResponse:
    return _respond(500, error_body("internal_error", "Something went wrong on the server."))


def register_error_handlers(app: FastAPI) -> None:
    """Make every error the app can produce use the ``error_body`` shape."""
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _request_invalid)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected)
