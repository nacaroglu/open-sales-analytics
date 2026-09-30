"""Structured JSON logging that cannot carry sales data or credentials.

Every record is written as one line holding one JSON object. Exception
messages are never written, only the class name and the stack frames, because
DuckDB and parsing errors can quote row values.
"""

import json
import logging
import sys
import time
from datetime import UTC, datetime

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import error_body
from app.tokens import is_valid_dataset_id

_HANDLER_FLAG = "_osa_json_handler"
_UNCAUGHT_MESSAGE = "Exception in ASGI application"
_MAX_FRAMES = 50
_COLLECTION_PATHS = ("/api/datasets", "/api/datasets/sample")
_DATASET_PREFIX = "/api/datasets/"

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
    chained = []
    link = exc.__cause__ or exc.__context__
    while link is not None and len(chained) < 10:
        chained.append(type(link).__name__)
        link = link.__cause__ or link.__context__
    if chained:
        details["chained"] = chained
    return details


def log_exception(logger: logging.Logger, message: str, exc: BaseException) -> None:
    """Log ``message`` at ERROR with the class and frames of ``exc``, not its message."""
    logger.error(message, extra={"fields": exception_details(exc)})


class JsonFormatter(logging.Formatter):
    """One JSON object per record; ``json`` escapes every control character."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if fields:
            entry.update(fields)
        if record.exc_info and record.exc_info[1] is not None and "exception" not in entry:
            entry.update(exception_details(record.exc_info[1]))
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


def _path_dataset_id(path: str) -> str | None:
    if not path.startswith(_DATASET_PREFIX):
        return None
    candidate = path[len(_DATASET_PREFIX):].split("/", 1)[0]
    return candidate if is_valid_dataset_id(candidate) else None


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
        state = scope.setdefault("state", {})
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
            self._log_request(scope, state, result["status"], started)

    @staticmethod
    def _log_request(scope: Scope, state: dict, status: int, started: float) -> None:
        path = scope.get("path", "")
        if scope.get("method") == "POST" and path in _COLLECTION_PATHS:
            dataset_id = state.get("created_dataset_id") if status == 201 else None
        else:
            dataset_id = _path_dataset_id(path)
        request_logger.log(
            logging.ERROR if status >= 500 else logging.INFO,
            "request",
            extra={
                "fields": {
                    "method": scope.get("method"),
                    "path": path,
                    "status": status,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                    "dataset_id": dataset_id,
                }
            },
        )
