# open-sales-analytics

Open Sales Analytics is a small self-hosted web application. You upload a CSV of completed sales lines and it shows
gross sales, orders, units, average order value, a sales trend and the top products, with a date range you can change.
Gross sales is quantity times unit price, summed over the lines in the chosen period. It has no refunds, discounts,
taxes or shipping in it.

Contents: [Run it with Docker](#run-it-with-docker) | [Configuration](#configuration) |
[Dataset contract](#dataset-contract) | [Currencies](#currencies) | [Privacy](#privacy) |
[Demo mode](#demo-mode) | [Limitations](#limitations) | [Architecture](#architecture) | [Development](#development)

## Run it with Docker

There is no published image, so you build it once from a checkout of this repository, then run it:

```sh
docker build -t open-sales-analytics .
docker run -p 8000:8000 open-sales-analytics
```

Open <http://localhost:8000>. You see the upload screen; **Try sample data** opens a dashboard with the sample file.
`curl http://localhost:8000/api/health` returns `{"status":"ok"}`.

The container runs as a non-root user (UID 10001) and keeps its datasets in `/data` (`DATASET_DIR=/data`). Without a
volume they are lost when the container is removed. To keep them, mount a named volume at `/data`:

```sh
docker run -p 8000:8000 -v osa-data:/data open-sales-analytics
```

With the volume, datasets survive `docker restart` and re-creating the container, on a best-effort basis, and each one
still expires after `DATASET_TTL_HOURS`. If you mount a host directory at `/data` instead of a named volume, it must
be writable by the container's non-root user (UID 10001), for example `sudo chown 10001 /path/to/dir`.

The image checks itself: `docker ps` shows `healthy` a few seconds after start, and `unhealthy` when `/api/health`
stops answering (checked every 10 s, 3 s timeout, 3 failures, 10 s start period). `docker stop` ends the server in
under a second with exit code 0, after stopping the background cleanup. The server sets no request timeout of its own
(uvicorn defaults apply), so a very slow upload ends only when the client gives up.

Pass a setting with `-e`, using a variable from the [table below](#configuration):

```sh
docker run -p 8000:8000 -e PUBLIC_DEMO_MODE=true open-sales-analytics
```

## Configuration

The server reads these environment variables when it starts. Every variable is optional.

| Variable | Type | Default | Effect |
| --- | --- | --- | --- |
| `DATASET_DIR` | path | `./tmp_datasets` (`/data` in the Docker image) | Directory that holds one DuckDB file per dataset. Created with private permissions if missing. |
| `DATASET_TTL_HOURS` | integer > 0 | `24` | Hours after which a dataset expires and is deleted. |
| `DATASET_TTL_SECONDS` | integer > 0 | unset | Test-only. When set, the lifetime in seconds, instead of `DATASET_TTL_HOURS`. The browser tests use it to see a real expiry. Leave it unset in production. |
| `MAX_UPLOAD_BYTES` | integer > 0 | `52428800` (50 MB) | Largest accepted upload, in bytes. A larger file is rejected with `file_too_large`. |
| `MAX_ROWS` | integer > 0 | `500000` | Most data rows (header not counted) in one upload. More is rejected with `too_many_rows`. |
| `CLEANUP_INTERVAL_MINUTES` | integer > 0 | `15` | How often the server removes expired datasets (it also does so once at startup). |
| `PUBLIC_DEMO_MODE` | boolean | `false` | `true` turns uploads off, see [Demo mode](#demo-mode). |
| `MAX_DATASETS` | integer > 0 | `200` | Most unexpired datasets the server holds. Creating one more (an upload or **Try sample data**) answers 503 `capacity_reached` until one expires or is deleted. |

Booleans accept `true`/`false`, `1`/`0` and `yes`/`no` in any letter case (`on`/`off`, `t`/`f` and `y`/`n` also work).

An invalid value makes the server refuse to start, with an error that names the variable. Invalid means not a number,
zero or negative, a decimal such as `1.5`, an empty string, or a boolean that is none of the spellings above. For
example, `MAX_ROWS=0 uv run uvicorn app.main:app --app-dir backend` exits with `MAX_ROWS  Input should be greater than 0`.

## Dataset contract

One row is one product line within one completed order. The file must have these six columns (the same table is on the
upload screen):

| Column | Type | Rule |
| --- | --- | --- |
| `order_id` | String | Required and non-empty. Used for distinct order counting. |
| `order_date` | Date | Required ISO calendar date in `YYYY-MM-DD` format. Must not be in the future. |
| `product_id` | String | Required and non-empty. Identifies the product. |
| `product_name` | String | Required and non-empty. One `product_id` must map to exactly one name within an upload. |
| `quantity` | Integer | Required and greater than zero. Zero and negative quantities are invalid. |
| `unit_price` | Decimal | Required and non-negative. A zero price is accepted with a warning; a negative price is invalid. |

File-level rules:

- UTF-8, comma-separated, one header row. The header is row 1 in error reports, so the first data row is row 2.
- Column names are matched after trimming spaces. Order does not matter. A column that is not one of the six is
  ignored, with a warning (`extra_column`).
- `(order_id, product_id)` is unique: the same product appears at most once per order.
- One name per `product_id` in the whole file.
- One currency per upload, chosen in the upload form (see [Currencies](#currencies)).
- Any invalid row rejects the whole file. Nothing is stored.
- At most 50 MB and 500,000 rows by default (the `MAX_UPLOAD_BYTES` and `MAX_ROWS` variables).
- Quantities are whole numbers up to 2,147,483,647. Prices are plain decimals (no currency symbol, no thousands
  separator) with at most 14 digits before and 4 after the point.

### A valid example

Save this as `example.csv`. It has three lines and two orders; order `A-1001` has two lines.

```csv
order_id,order_date,product_id,product_name,quantity,unit_price
A-1001,2025-03-01,P-10,Ceramic Mug,2,12.50
A-1001,2025-03-01,P-20,Travel Tumbler,1,24.00
A-1002,2025-03-02,P-10,Ceramic Mug,1,12.50
```

With the app running on port 8000, import it through the API:

```sh
curl -F currency=USD -F file=@example.csv http://localhost:8000/api/datasets
```

The answer is `201` with `"warnings":[]`, a `dataset_id`, a `token` and the first summary. Gross sales here is 61.50
from 2 orders and 4 units.

### Invalid examples

Each is a small change to the valid file. The app answers `422` with the error code `validation_failed` and a list of
errors; the `code` of each error is the one in this table. Each error also carries the row number and the column.

| Change to the valid file | Error `code` | Row |
| --- | --- | --- |
| Remove `unit_price` from the header (and the last value of every row) | `missing_column` | none (file level) |
| Change the date `2025-03-02` to `2025-13-02` | `invalid_date` | 4 |
| Change the quantity of the last row from `1` to `0` | `invalid_quantity` | 4 |
| Repeat the last row | `duplicate_line` | 5 |

### Error codes

The report lists the first 100 errors and gives the total count (`error_count`).

| Code | Cause |
| --- | --- |
| `file_too_large` | The file is larger than `MAX_UPLOAD_BYTES`. |
| `empty_file` | The file is empty. |
| `invalid_encoding` | The file is not valid UTF-8. |
| `malformed_csv` | The file cannot be read as CSV (for example, a single field longer than 131,072 characters). |
| `too_many_rows` | More than `MAX_ROWS` data rows. |
| `no_data_rows` | There is a header but no data rows. |
| `missing_column` | One of the six required columns is not in the header. |
| `duplicate_column` | A required column appears more than once in the header. |
| `missing_value` | A required value is blank. |
| `invalid_date` | `order_date` is not a real date written `YYYY-MM-DD`. |
| `future_date` | `order_date` is after today (UTC). |
| `invalid_quantity` | `quantity` is not a whole number from 1 to 2,147,483,647. |
| `invalid_price` | `unit_price` is not a plain decimal within 14 digits before and 4 after the point. |
| `negative_price` | `unit_price` is below zero. |
| `malformed_row` | The row has a different number of values than the header. |
| `duplicate_line` | The same `order_id` and `product_id` appear on an earlier row. |
| `conflicting_product_name` | One `product_id` has more than one `product_name`. |

A request can also fail before the file is read: a currency that is not in the list answers `400 invalid_request`.

### Warnings

Warnings do not reject the file. They come back in the `warnings` list of the `201` answer and on the upload screen.

| Code | Meaning |
| --- | --- |
| `extra_column` | The file has a column that is not one of the six, for example a `note` column. It is ignored and not stored. |
| `zero_price` | One or more lines have a unit price of 0. They are imported and count as orders and units, with no gross sales. |

### Sample data

Download a valid sample file at <http://localhost:8000/api/sample.csv> (the upload screen links it as **Download
sample CSV**). **Try sample data** on the upload screen imports the same file in USD without any upload.

## Trend buckets

The trend groups gross sales by calendar bucket. The granularity depends only on the selected range, counting both
end dates: up to 90 days is daily, over 90 days through 730 days is weekly, longer is monthly. The API returns
`bucket_start` per bucket (the bucket's first day) and no coverage field.

- The range is inclusive: the start date and the end date are both in it.
- Weeks run Monday to Sunday; a weekly bucket's `bucket_start` is its Monday. Months are calendar months.
- A bucket the range cuts (a first week or month that starts before the start date, a last one that ends after the
  end date) is a partial period. The chart works this out from the range and the calendar, so a day with no sales still
  counts as covered. A one-day daily bucket is always whole (the data holds dates only); a one-day slice of a week or
  month is partial. A range inside one week or month shows that bucket as partial.
- Partial presentation: the axis label of a partial week or month shows the dates it covers (`29–31 Dec`,
  `10–31 Mar 2025`) instead of `Week of 29 Dec` or the month name, the point is hollow, a note under the chart says
  so, and the tooltip adds the year and `Partial period: <covered dates>`. A whole bucket has none of these.
- Only rows inside the range are summed, so a partial bucket holds the sales of the dates it covers.

## Currencies

The currency is chosen in the upload form: USD, EUR, GBP, TRY, CAD, AUD, JPY, CHF, SEK, PLN. It is only a label for
the amounts. There is no conversion and no exchange rate. Any other code is refused with `400 invalid_request`.

## Privacy

- The raw CSV is deleted as soon as the import ends, on success and on failure.
- Only the six columns are stored, in one DuckDB file per dataset under `DATASET_DIR`, with private permissions
  (`0600` for the file, `0700` for the directories).
- A dataset is deleted after `DATASET_TTL_HOURS` (24 by default) by a cleanup at startup and then every
  `CLEANUP_INTERVAL_MINUTES`, or at once when you click **Analyze another file**.
- Access needs a random bearer token. The browser keeps it in `sessionStorage`, so it is gone when the tab closes.
  The server keeps only a SHA-256 hash of it.
- The logs are one JSON line per request with the method, path, status, duration and the dataset ID. The dataset ID is
  logged on purpose, so a request can be traced; it is not a secret and cannot be used without the token. The logs
  never contain tokens, file contents, file names, product names or order IDs. Error logs hold exception class names
  and stack frames, never exception messages.
- Nothing is sent to other services.

## Demo mode

`PUBLIC_DEMO_MODE=true` is for a public server that should not take other people's files:

- `POST /api/datasets` answers 403 `upload_disabled` without reading the body.
- **Try sample data** and the sample download keep working.
- The upload screen shows the file format and **Try sample data** only, no file or currency field, and says that
  uploads are available in the self-hosted version.
- `GET /api/config` returns `{"public_demo_mode":true,...}`, which is how the screen knows.
- `MAX_DATASETS` protects the disk on a public server: every click on **Try sample data** creates a dataset, and at the
  cap it answers 503 `capacity_reached`.

## Limitations

- One instance only. There is no horizontal scaling: datasets are files on that instance's disk.
- Surviving a restart is best effort, and only when `DATASET_DIR` is on a volume.
- No accounts and no sharing. A dataset is reachable only with its token, which stays in one browser tab.
- One currency per file.
- Gross sales only: no refunds, discounts, taxes or shipping.
- 50 MB and 500,000 rows by default.
- Desktop and tablet widths (768 px and up). Phones are not supported (see
  [`_docs/design-system.md`](_docs/design-system.md)).

## Architecture

A React (Vite) front end with Recharts talks JSON to a FastAPI back end. Each dataset is one DuckDB file under
`DATASET_DIR`; validation and analytics are SQL over that file. An in-process background task removes expired
datasets. The Docker image is a single container in which FastAPI serves both the API and the built front end from one
origin on port 8000. The full specification is in [`_docs/plan.md`](_docs/plan.md) (architecture in section 7), and the
backlog is in [`_docs/tasks.md`](_docs/tasks.md).

## Development

How work is organized: [`_docs/process.md`](_docs/process.md). Testing conventions:
[`_docs/testing-guidelines.md`](_docs/testing-guidelines.md).

From the repository root:

```sh
uv sync
uv run pytest
```

Lint and type checks (the same commands CI runs; `uv sync` installs `ruff` and `mypy` as dev dependencies):

```sh
uv run ruff check backend
uv run ruff format --check backend   # `uv run ruff format backend` fixes it
uv run mypy backend/app
```

Dependency scan (the same two commands the CI `dependency-scan` job runs; `uvx` runs `pip-audit` without making it a
project dependency):

```sh
uv export --locked --no-emit-project --format requirements-txt -o /tmp/requirements.txt
uvx pip-audit@2.10.1 -r /tmp/requirements.txt --no-deps --disable-pip
(cd frontend && npm audit --audit-level=high)
```

Start the backend (serves on http://127.0.0.1:8000):

```sh
uv run uvicorn app.main:app --app-dir backend
```

Check it: `curl http://127.0.0.1:8000/api/health` returns `{"status":"ok"}`. To serve the built front end from the
same origin without Docker, run `npm run build` in `frontend/` first (see below), then start the backend as above and
open <http://127.0.0.1:8000>.

### Frontend

Requires Node 22 or newer. From `frontend/`:

```sh
npm ci            # install
npm run dev       # dev server on http://localhost:5173
npm test          # Vitest, single run
npm run lint      # ESLint
npm run typecheck # tsc --noEmit (TypeScript 7)
npm run build     # type check, then the production bundle in frontend/dist
```

`npm run dev` proxies `/api` to the backend on port 8000, so start the backend too.

### Dependency scanning

CI scans both lockfiles on every pull request and every push to `main`:

| Ecosystem | Tool and input | Fails CI on |
| --- | --- | --- |
| Python | `pip-audit` over `uv.lock` (runtime and dev packages) | any known vulnerability (pip-audit has no severity filter) |
| npm | `npm audit --audit-level=high` over `frontend/package-lock.json` | high and critical advisories; low and moderate are shown in the log but do not fail |

A scanner that errors (no network, bad input) also fails the job; the steps have no `|| true` and no
`continue-on-error`. There is no ignore list. If an advisory has no fix yet, the way out is a reviewed pull request
that pins an exception in the scan command with the advisory ID and the reason next to it (`pip-audit --ignore-vuln ID`
or removing the package); it is never a silent skip. Caches hold package downloads and the Playwright browser only;
no dataset, upload, secret or DuckDB file is cached or uploaded as an artifact.

### Browser test

A small Playwright suite (Chromium, `frontend/e2e/`) covers the primary journeys: Try sample data, a valid upload,
an invalid upload, the date range and Reset, Analyze another file, and an expired dataset.
Install the browser once (about 150 MB, stored outside the repository), then run it from `frontend/`:

```sh
npx playwright install chromium
npx playwright install-deps chromium   # Linux only: system libraries, needs sudo; CI runs it too
npm run e2e
```

`npm run e2e` starts the backend (port 8000) and the Vite dev server (port 5173) itself, with a temporary dataset
directory, and stops them afterwards. Both ports must be free. To test an app that is already running (for example
the container), set `E2E_BASE_URL`; no server is started then. That app must run with `DATASET_TTL_SECONDS=60`, because
the expiry journey waits (bounded polling) for a real expiry:

```sh
docker build -t open-sales-analytics .   # from the repository root
docker run -d --name oca -p 8000:8000 -e DATASET_TTL_SECONDS=60 open-sales-analytics
curl -f http://localhost:8000/api/health   # answers {"status":"ok"}; repeat for a few seconds until it does
curl -f http://localhost:8000/d/anything | grep -i '<div id="root"'   # the single-page app
E2E_BASE_URL=http://localhost:8000 npm run e2e
docker rm -f oca
```

On failure a trace and a screenshot are saved in `frontend/test-results/` (open a trace with `npx playwright show-trace`).
With `CI` set (as on GitHub Actions) no trace is recorded, because a trace contains the network responses, and CI uploads
only the failure screenshots.
