"""Structured JSON logging that cannot carry sales data or credentials.

Every record is written as one line holding one JSON object. Exception
messages are never written, only the class name and the stack frames, because
DuckDB and parsing errors can quote row values.
"""

import json
import logging
import re
import sys
import time
from datetime import UTC, datetime

from opentelemetry import trace
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import get_settings
from app.errors import error_body

_HANDLER_FLAG = "_osa_json_handler"
_UNCAUGHT_MESSAGE = "Exception in ASGI application"
_MAX_FRAMES = 50
_FIELD_ALLOWLIST = {
    "event",
    "operation",
    "outcome",
    "error_code",
    "method",
    "route",
    "status",
    "duration_ms",
    "exception",
    "frames",
    "chained",
}
_SAFE_VERSION = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "CONNECT", "TRACE"}
_SAFE_EXCEPTION_EVENTS = {
    "unhandled exception",
    "dataset creation failed",
    "sample dataset import failed",
    "sample dataset summary failed",
}
_CLEANUP_EXCEPTION_CLASSES = {
    "OSError",
    "PermissionError",
    "FileNotFoundError",
    "NotADirectoryError",
    "IsADirectoryError",
    "RuntimeError",
    "OtherError",
}
_SAFE_MESSAGES = _SAFE_EXCEPTION_EVENTS | {
    "request",
    "cleanup file removal failed",
    "cleanup directory removal failed",
    "cleanup sweep completed",
    "cleanup sweep failed",
    "Dataset creation refused because the server is at capacity.",
    "Upload rejected because public demo mode is enabled.",
}

request_logger = logging.getLogger("osa.request")
error_logger = logging.getLogger("osa.error")


def exception_details(exc: BaseException) -> dict:
    """Class names and stack frames of ``exc`` and its chain; never any message."""
    frames = []
    tb = exc.__traceback__
    while tb is not None:
        code = tb.tb_frame.f_code
        frames.append({"file": code.co_filename, "line": tb.tb_lineno, "function": code.co_name})
        tb = tb.tb_next
    details: dict = {"exception": type(exc).__name__, "frames": frames[-_MAX_FRAMES:]}
    chained: list[str] = []
    link = exc.__cause__ or exc.__context__
    while link is not None and len(chained) < 10:
        chained.append(type(link).__name__)
        link = link.__cause__ or link.__context__
    if chained:
        details["chained"] = chained
    return details


def log_exception(logger: logging.Logger, message: str, exc: BaseException) -> None:
    """Log ``message`` at ERROR with the class and frames of ``exc``, not its message."""
    logger.error(message, extra={"osa_exception": exc, "osa_event": message})


class JsonFormatter(logging.Formatter):
    """One JSON object per record; ``json`` escapes every control character."""

    def format(self, record: logging.LogRecord) -> str:
        settings = get_settings()
        version = settings.osa_version
        if not _SAFE_VERSION.fullmatch(version):
            version = "unknown"
        span_context = trace.get_current_span().get_span_context()
        message = (
            record.msg
            if isinstance(record.msg, str) and not record.args and record.msg in _SAFE_MESSAGES
            else "application event"
        )
        entry: dict = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "severity": record.levelname.lower(),
            "logger": record.name,
            "message": message,
            "event": "application.log",
            "service_name": "open-sales-analytics",
            "environment": settings.osa_environment,
            "version": version,
        }
        if span_context.is_valid:
            entry["trace_id"] = f"{span_context.trace_id:032x}"
            entry["span_id"] = f"{span_context.span_id:016x}"
        fields = getattr(record, "fields", None)
        if fields and record.name == "osa.request":
            method = fields.get("method")
            route = fields.get("route")
            entry.update(
                {
                    "event": "http.request",
                    "operation": "http.request",
                    "outcome": fields.get("outcome")
                    if fields.get("outcome") in {"success", "error"}
                    else "unknown",
                    "method": method if method in _METHODS else "OTHER",
                    "route": route
                    if isinstance(route, str)
                    and len(route) <= 128
                    and route == route.lower()
                    and re.fullmatch(r"[A-Za-z0-9_./{}:-]+", route)
                    else "unmatched",
                    "status": fields.get("status")
                    if isinstance(fields.get("status"), int) and 100 <= fields["status"] <= 599
                    else 0,
                    "duration_ms": fields.get("duration_ms")
                    if isinstance(fields.get("duration_ms"), (int, float))
                    and 0 <= fields["duration_ms"] <= 86_400_000
                    else 0,
                }
            )
        elif fields and record.name == "app.cleanup" and fields.get("event") == "cleanup.sweep":
            entry["event"] = "cleanup.sweep"
            entry["operation"] = "cleanup.sweep"
            for key in ("datasets_removed", "temporary_files_removed"):
                value = fields.get(key)
                if isinstance(value, int) and 0 <= value <= 1_000_000:
                    entry[key] = value
        elif (
            fields
            and record.name == "app.cleanup"
            and fields.get("event")
            in {
                "cleanup.file_removal_failed",
                "cleanup.directory_removal_failed",
                "cleanup.sweep_failed",
            }
        ):
            entry["event"] = fields["event"]
            entry["operation"] = "cleanup"
            exception_class = fields.get("exception_class")
            if exception_class in _CLEANUP_EXCEPTION_CLASSES:
                entry["exception_class"] = exception_class
        exception = getattr(record, "osa_exception", None)
        if exception is None and record.exc_info:
            exception = record.exc_info[1]
        if exception is not None:
            event = getattr(record, "osa_event", None)
            entry["message"] = event if event in _SAFE_EXCEPTION_EVENTS else "operation failed"
            details = exception_details(exception)
            entry.update({key: value for key, value in details.items() if key in _FIELD_ALLOWLIST})
        return json.dumps(entry, ensure_ascii=True, default=str)


class _StderrHandler(logging.StreamHandler):
    """Writes to whatever ``sys.stderr`` is at the moment of each record."""

    def __init__(self) -> None:
        logging.Handler.__init__(self)

    @property
    def stream(self):
        return sys.stderr


class _DropUvicornTraceback(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage() != _UNCAUGHT_MESSAGE


class _DropAll(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return False


def configure_logging() -> None:
    """Send all records to stderr as JSON at INFO. Safe to call any number of times."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(getattr(handler, _HANDLER_FLAG, False) for handler in root.handlers):
        handler = _StderrHandler()
        handler.setFormatter(JsonFormatter())
        setattr(handler, _HANDLER_FLAG, True)
        root.addHandler(handler)

    access = logging.getLogger("uvicorn.access")
    access.disabled = True
    access.propagate = False
    access.handlers.clear()
    if not any(isinstance(f, _DropAll) for f in access.filters):
        access.addFilter(_DropAll())

    # Backstop: the middleware never re-raises, so this record should not occur.
    uvicorn_error = logging.getLogger("uvicorn.error")
    if not any(isinstance(f, _DropUvicornTraceback) for f in uvicorn_error.filters):
        uvicorn_error.addFilter(_DropUvicornTraceback())


class RequestLogMiddleware:
    """Writes one request line per request and answers unhandled errors itself.

    An unhandled exception is logged once (class and frames) and answered with
    the standard 500 body, without re-raising, so uvicorn never logs it again.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        result = {"status": 500, "sent": False}

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                result["status"] = message["status"]
                result["sent"] = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:  # noqa: BLE001 - the last line of defence
            result["status"] = 500
            log_exception(error_logger, "unhandled exception", exc)
            if not result["sent"]:
                response = JSONResponse(
                    error_body("internal_error", "Something went wrong on the server."),
                    status_code=500,
                )
                await response(scope, receive, send_wrapper)
        finally:
            self._log_request(scope, result["status"], started)

    @staticmethod
    def _log_request(scope: Scope, status: int, started: float) -> None:
        route = getattr(scope.get("route"), "path", "unmatched")
        if not isinstance(route, str) or len(route) > 128:
            route = "unmatched"
        method = scope.get("method")
        method = method if method in _METHODS else "OTHER"
        request_logger.log(
            logging.ERROR if status >= 500 else logging.INFO,
            "request",
            extra={
                "fields": {
                    "event": "http.request",
                    "operation": "http.request",
                    "outcome": "failure"
                    if status >= 500
                    else "rejected"
                    if status >= 400
                    else "success",
                    "method": method,
                    "route": route,
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                }
            },
        )
