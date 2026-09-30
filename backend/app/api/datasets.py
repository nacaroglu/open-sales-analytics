import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import MultipartParser, parse_options_header

from app.auth import AuthorizedDataset, require_dataset
from app.config import Settings, get_settings
from app.currencies import CURRENCIES, is_valid_currency
from app.errors import ApiError
from app.ingest import CreatedDataset, ingest_csv, new_upload_path

router = APIRouter(prefix="/api")

SAMPLE_CSV = Path(__file__).resolve().parent.parent / "sample" / "sample_sales.csv"
SAMPLE_CURRENCY = "USD"

_MAX_FIELD_BYTES = 256  # the only text field is a currency code


def _invalid(message: str) -> ApiError:
    return ApiError(400, "invalid_request", message)


class _Upload:
    """Reads a multipart body as it streams in.

    The ``file`` part goes straight to a server-named temp file, and reading
    stops once ``max_bytes + 1`` bytes of it are written, so an oversized file
    is never stored whole. Every other part is ignored except ``currency``. The
    client's file name is never read. A bad currency is refused as soon as its
    part is complete, so it is before any temp file when it comes first, as
    forms normally send it.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.max_bytes = settings.max_upload_bytes + 1
        self.path: Path | None = None
        self.currency: str | None = None
        self.file_done = False
        self.full = False
        self._written = 0
        self._target = None  # "file", "currency" or None, for the current part
        self._out = None
        self._field = bytearray()
        self._name = bytearray()
        self._value = bytearray()
        self._disposition = b""

    # parser callbacks
    def on_part_begin(self) -> None:
        self._target = None
        self._disposition = b""
        self._field.clear()
        self._name.clear()
        self._value.clear()

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._name += data[start:end]

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._value += data[start:end]

    def on_header_end(self) -> None:
        if bytes(self._name).lower() == b"content-disposition":
            self._disposition = bytes(self._value)
        self._name.clear()
        self._value.clear()

    def on_headers_finished(self) -> None:
        _, params = parse_options_header(self._disposition)
        name = params.get(b"name")
        if name == b"file":
            if self.path is not None:
                raise _invalid("Send exactly one file part.")
            if self.currency is not None and not is_valid_currency(self.currency):
                raise _invalid(_currency_message())
            self._target = "file"
            self.path = new_upload_path(self.settings)
            self._out = open(self.path, "xb")
        elif name == b"currency":
            if self.currency is not None:
                raise _invalid("Send exactly one currency field.")
            self._target = "currency"

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        chunk = data[start:end]
        if self._target == "file":
            chunk = chunk[: self.max_bytes - self._written]
            self._out.write(chunk)
            self._written += len(chunk)
            self.full = self._written >= self.max_bytes
        elif self._target == "currency":
            self._field += chunk
            if len(self._field) > _MAX_FIELD_BYTES:
                raise _invalid(_currency_message())

    def on_part_end(self) -> None:
        if self._target == "file":
            self._out.close()
            self._out = None
            self.file_done = True
        elif self._target == "currency":
            try:
                self.currency = self._field.decode("utf-8")
            except UnicodeDecodeError:
                raise _invalid(_currency_message()) from None
            if not is_valid_currency(self.currency):
                raise _invalid(_currency_message())

    def close(self) -> None:
        if self._out is not None:
            self._out.close()
            self._out = None


def _currency_message() -> str:
    return "The currency must be one of " + ", ".join(CURRENCIES) + "."


async def _receive(request: Request, upload: _Upload) -> None:
    content_type, options = parse_options_header(request.headers.get("content-type", ""))
    boundary = options.get(b"boundary")
    if content_type != b"multipart/form-data" or not boundary:
        raise _invalid("Send the file and currency as multipart/form-data.")

    parser = MultipartParser(
        boundary,
        {
            "on_part_begin": upload.on_part_begin,
            "on_header_field": upload.on_header_field,
            "on_header_value": upload.on_header_value,
            "on_header_end": upload.on_header_end,
            "on_headers_finished": upload.on_headers_finished,
            "on_part_data": upload.on_part_data,
            "on_part_end": upload.on_part_end,
        },
    )
    try:
        async for chunk in request.stream():
            parser.write(chunk)
            if upload.full:
                break
        else:
            parser.finalize()
    except MultipartParseError:
        raise _invalid("The request body is not valid multipart/form-data.") from None
    finally:
        upload.close()

    if upload.path is None:
        raise _invalid("A file part named 'file' is required.")
    if not upload.file_done and not upload.full:
        raise _invalid("The request body ended before the file was complete.")
    if upload.currency is None:
        raise _invalid(_currency_message())


@router.post("/datasets", status_code=201)
async def create_dataset(request: Request, settings: Settings = Depends(get_settings)):
    upload = _Upload(settings)
    try:
        await _receive(request, upload)
        outcome = await run_in_threadpool(ingest_csv, upload.path, upload.currency, settings)
    except ApiError:
        raise
    except Exception:
        raise ApiError(500, "internal_error", "Something went wrong on the server.") from None
    finally:
        # ingest_csv deletes the file itself; this covers every earlier exit.
        if upload.path is not None:
            upload.path.unlink(missing_ok=True)

    if isinstance(outcome, CreatedDataset):
        return JSONResponse(
            {
                "dataset_id": outcome.dataset_id,
                "token": outcome.token,
                "meta": outcome.meta,
                "warnings": outcome.warnings,
            },
            status_code=201,
            headers={"Cache-Control": "no-store"},
        )
    raise ApiError(
        422,
        "validation_failed",
        "The file has problems that must be fixed before it can be used.",
        details=outcome.to_dict(),
    )


def _ingest_sample(settings: Settings) -> CreatedDataset | None:
    """Import a copy of the bundled sample; ``None`` if the sample is not clean.

    The copy is what gets imported, because the import deletes its input.
    """
    copy = new_upload_path(settings)
    try:
        shutil.copyfile(SAMPLE_CSV, copy)
        outcome = ingest_csv(copy, SAMPLE_CURRENCY, settings)
    finally:
        copy.unlink(missing_ok=True)
    return outcome if isinstance(outcome, CreatedDataset) else None


@router.post("/datasets/sample", status_code=201)
async def create_sample_dataset(settings: Settings = Depends(get_settings)):
    # The request body and any form fields are deliberately never read.
    try:
        outcome = await run_in_threadpool(_ingest_sample, settings)
    except Exception:
        outcome = None
    if outcome is None:
        raise ApiError(500, "sample_unavailable", "The sample dataset is not available right now.")
    return JSONResponse(
        {
            "dataset_id": outcome.dataset_id,
            "token": outcome.token,
            "meta": outcome.meta,
            "warnings": outcome.warnings,
        },
        status_code=201,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/datasets/{id}")
def get_dataset_meta(dataset: AuthorizedDataset = Depends(require_dataset)):
    return JSONResponse(dataset.meta, headers={"Cache-Control": "no-store"})
