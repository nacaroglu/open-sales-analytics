import logging
import re
import shutil
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, JSONResponse, Response
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import MultipartParser, parse_options_header

from app.analytics.kpis import read_kpis
from app.analytics.top_products import read_top_products
from app.analytics.trend import read_trend
from app.auth import AuthorizedDataset, get_now, require_dataset
from app.capacity import count_live_datasets
from app.config import Settings, get_settings
from app.currencies import CURRENCIES, is_valid_currency
from app.errors import ApiError
from app.importer import dataset_path
from app.ingest import CreatedDataset, ingest_csv, new_upload_path
from app.logging_config import log_exception
from app.schema import open_dataset_readonly

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

SAMPLE_CSV = Path(__file__).resolve().parent.parent / "sample" / "sample_sales.csv"
SAMPLE_CURRENCY = "USD"

_MAX_FIELD_BYTES = 256  # the only text field is a currency code
TOP_PRODUCTS_COUNT = 10
_DATE_FORM = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


def _invalid(message: str) -> ApiError:
    return ApiError(400, "invalid_request", message)


def _money(value: Decimal) -> str:
    return f"{value:.4f}"


def build_summary(connection, meta: dict, start: date, end: date) -> dict:
    """The analytics response body for ``start`` to ``end`` (both inside the dataset)."""
    kpis = read_kpis(connection, start, end)
    trend = read_trend(connection, start, end)
    top = read_top_products(connection, start, end, TOP_PRODUCTS_COUNT)
    return {
        "range": {"start": start.isoformat(), "end": end.isoformat()},
        "currency": meta["currency"],
        "granularity": trend["granularity"],
        "kpis": {
            "gross_sales": _money(kpis["gross_sales"]),
            "orders": kpis["orders"],
            "units_sold": kpis["units_sold"],
            "average_order_value": _money(kpis["average_order_value"]),
        },
        "trend": [
            {"bucket_start": b["bucket_start"].isoformat(), "gross_sales": _money(b["gross_sales"])}
            for b in trend["buckets"]
        ],
        "top_products": [
            {
                "product_id": p["product_id"],
                "product_name": p["product_name"],
                "gross_sales": _money(p["gross_sales"]),
                "units_sold": p["units_sold"],
                "distinct_orders": p["distinct_orders"],
            }
            for p in top
        ],
    }


def _remove_dataset_files(target: Path) -> None:
    """Delete a dataset file and its ``.wal`` sibling; raises FileNotFoundError if the file is gone."""
    target.with_name(target.name + ".wal").unlink(missing_ok=True)
    target.unlink()


def _full_range_summary(settings: Settings, created: CreatedDataset) -> dict:
    """The summary for a just-created dataset; removes the dataset if it cannot be computed."""
    target = dataset_path(settings, created.dataset_id)
    try:
        connection = open_dataset_readonly(target)
        try:
            first = date.fromisoformat(created.meta["date_range"]["min"])
            last = date.fromisoformat(created.meta["date_range"]["max"])
            return build_summary(connection, created.meta, first, last)
        finally:
            connection.close()
    except BaseException:
        try:
            _remove_dataset_files(target)
        except FileNotFoundError:
            pass
        raise


def _created_body(created: CreatedDataset, summary: dict) -> dict:
    return {
        "dataset_id": created.dataset_id,
        "token": created.token,
        "meta": created.meta,
        "warnings": created.warnings,
        "initial_summary": summary,
    }


def _internal_error() -> ApiError:
    return ApiError(500, "internal_error", "Something went wrong on the server.")


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


async def _ensure_capacity(settings: Settings, now: datetime) -> None:
    """503 when the server already holds MAX_DATASETS live datasets.

    The check and the creation are not one atomic step and there is no lock on
    purpose: creates that arrive together can all pass, so the count may briefly
    exceed MAX_DATASETS by at most the number of requests running at once (the
    worker-thread limit). The goal is a bound on disk use, not an exact number,
    and a lock would serialize the multi-second imports.
    """
    live = await run_in_threadpool(count_live_datasets, settings, now, settings.max_datasets)
    if live >= settings.max_datasets:
        logger.info("Dataset creation refused because the server is at capacity.")
        raise ApiError(
            503,
            "capacity_reached",
            "The server is holding the maximum number of datasets right now. Try again later.",
        )


@router.post("/datasets", status_code=201)
async def create_dataset(
    request: Request,
    settings: Settings = Depends(get_settings),
    now: datetime = Depends(get_now),
):
    if settings.public_demo_mode:
        # First thing: the body is never read, parsed or stored.
        logger.info("Upload rejected because public demo mode is enabled.")
        raise ApiError(
            403,
            "upload_disabled",
            "Uploads are disabled on this demo. Upload your own file with the self-hosted version.",
        )
    await _ensure_capacity(settings, now)
    upload = _Upload(settings)
    try:
        await _receive(request, upload)
        outcome = await run_in_threadpool(ingest_csv, upload.path, upload.currency, settings)
        summary = (
            await run_in_threadpool(_full_range_summary, settings, outcome)
            if isinstance(outcome, CreatedDataset)
            else None
        )
    except ApiError:
        raise
    except Exception as exc:
        log_exception(logger, "dataset creation failed", exc)
        raise _internal_error() from None
    finally:
        # ingest_csv deletes the file itself; this covers every earlier exit.
        if upload.path is not None:
            upload.path.unlink(missing_ok=True)

    if isinstance(outcome, CreatedDataset):
        request.state.created_dataset_id = outcome.dataset_id
        return JSONResponse(
            _created_body(outcome, summary),
            status_code=201,
            headers={"Cache-Control": "no-store"},
        )
    raise ApiError(
        422,
        "validation_failed",
        "The file has problems that must be fixed before it can be used.",
        details=outcome.to_dict(),
    )


def _sample_unavailable() -> ApiError:
    return ApiError(500, "sample_unavailable", "The sample dataset is not available right now.")


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
async def create_sample_dataset(
    request: Request,
    settings: Settings = Depends(get_settings),
    now: datetime = Depends(get_now),
):
    # The request body and any form fields are deliberately never read.
    await _ensure_capacity(settings, now)
    try:
        outcome = await run_in_threadpool(_ingest_sample, settings)
    except Exception as exc:
        log_exception(logger, "sample dataset import failed", exc)
        outcome = None
    if outcome is None:
        raise _sample_unavailable()
    try:
        summary = await run_in_threadpool(_full_range_summary, settings, outcome)
    except Exception as exc:
        log_exception(logger, "sample dataset summary failed", exc)
        raise _internal_error() from None
    request.state.created_dataset_id = outcome.dataset_id
    return JSONResponse(
        _created_body(outcome, summary),
        status_code=201,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/sample.csv")
def download_sample_csv() -> FileResponse:
    # Public on purpose: no token, no settings, nothing written to DATASET_DIR.
    # SAMPLE_CSV is read here, not at import, so a test can point it elsewhere.
    if not SAMPLE_CSV.is_file():
        raise _sample_unavailable()
    return FileResponse(SAMPLE_CSV, media_type="text/csv", filename="sample_sales.csv")


@router.get("/datasets/{id}")
def get_dataset_meta(dataset: AuthorizedDataset = Depends(require_dataset)):
    return JSONResponse(dataset.meta, headers={"Cache-Control": "no-store"})


def _invalid_range(message: str) -> ApiError:
    return ApiError(400, "invalid_range", message)


def _parse_day(name: str, text: str) -> date:
    if not _DATE_FORM.fullmatch(text):
        raise _invalid_range(f"{name} must be a date written YYYY-MM-DD.")
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise _invalid_range(f"{name} is not a real date.") from None


@router.get("/datasets/{id}/analytics")
def get_dataset_analytics(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    dataset: AuthorizedDataset = Depends(require_dataset),
    settings: Settings = Depends(get_settings),
):
    first = date.fromisoformat(dataset.meta["date_range"]["min"])
    last = date.fromisoformat(dataset.meta["date_range"]["max"])
    range_start = first if start is None else _parse_day("start", start)
    range_end = last if end is None else _parse_day("end", end)
    if range_start > range_end:
        raise _invalid_range("start must not be after end.")
    if range_start < first or range_end > last:
        raise _invalid_range(f"The range must be within {first.isoformat()} and {last.isoformat()}.")

    connection = open_dataset_readonly(dataset_path(settings, dataset.id))
    try:
        body = build_summary(connection, dataset.meta, range_start, range_end)
    finally:
        connection.close()
    return JSONResponse(body, headers={"Cache-Control": "no-store"})


@router.delete("/datasets/{id}", status_code=204)
def delete_dataset(
    dataset: AuthorizedDataset = Depends(require_dataset),
    settings: Settings = Depends(get_settings),
):
    try:
        _remove_dataset_files(dataset_path(settings, dataset.id))
    except FileNotFoundError:
        # Removed by someone else after the authorisation check.
        raise ApiError(404, "not_found", "The dataset was not found.") from None
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
