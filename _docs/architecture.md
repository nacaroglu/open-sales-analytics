# Architecture

Languages: [English](architecture.md) | [Türkçe](architecture.tr-TR.md) | [Deutsch](architecture.de-DE.md) | [Русский](architecture.ru-RU.md) | [Español](architecture.es-ES.md) | [简体中文](architecture.zh-CN.md) | [日本語](architecture.ja-JP.md)

Open Sales Analytics is a single-origin React/Vite application served by FastAPI. The frontend keeps the dataset
identifier and bearer token in one browser tab's `sessionStorage`; it sends date-range and comparison choices to the
backend and renders aggregate responses. The backend is stateless between requests except for one DuckDB file per
dataset and a bounded process-local response cache.

## Repository domains

| Domain | Real path | Responsibility |
| --- | --- | --- |
| API and lifecycle | `backend/app/api/`, `backend/app/auth.py`, `backend/app/cleanup.py` | Upload/sample creation, authorization, expiry, metadata and response envelopes |
| Overview | `backend/app/analytics/overview/` | Gross sales, distinct orders, units, average order value, trends and comparisons |
| Products | `backend/app/analytics/products/` | Rankings, share/Pareto, growth, dormancy, price history, penetration and basket affinity |
| Customers | `backend/app/analytics/customers/` | Coverage, customer aggregates, cohorts, RFM and projection |
| Shared periods and availability | `backend/app/analytics/shared/` | Inclusive date filters, comparison periods, bucket choice, availability and metric definitions |
| Import and persistence | `backend/app/ingest.py`, `backend/app/importer.py`, `backend/app/schema.py` | Validate a CSV, build facts, write the dataset file and remove staging data |
| Web UI | `frontend/src/` | Upload, dashboard navigation, accessible states, tables and chart text alternatives |

The authoritative metric formulas and states are in `backend/app/analytics/shared/metrics.py`; the human-readable
catalogue is [_docs/metrics.md](metrics.md). The Phase 3 product specification is
[_docs/open_sales_analytics_phase_3_spec.md](open_sales_analytics_phase_3_spec.md).

## Dataset file

Each upload becomes one private DuckDB file under `DATASET_DIR`. Import computes reusable facts once; request-time
queries filter those facts by the selected inclusive range and comparison period.

| Table | Columns | Meaning |
| --- | --- | --- |
| `line_items` | `order_id`, `order_date`, `product_id`, `product_name`, `quantity`, `unit_price`, nullable `customer_id` | Validated source lines; one row per product line, with the optional opaque customer ID |
| `order_facts` | `order_id`, `first_order_date`, `last_order_date`, `line_count`, `units`, `gross_sales` | One row per order and its lifetime line/order totals |
| `product_facts` | `product_id`, `product_name`, `first_sale_date`, `last_sale_date`, `lifetime_gross_sales`, `lifetime_units`, `lifetime_orders` | One row per product and lifetime portfolio facts |
| `customer_facts` | `customer_id`, `first_order_date`, `acquisition_month`, `first_day_orders`, `last_order_date`, `lifetime_orders`, `lifetime_units`, `lifetime_gross_sales` | One row per identified customer; absent or empty for six-column data |
| `dataset_meta` | `id`, `currency`, `created_at`, `expires_at`, `token_hash`, `row_count`, `has_customer_id`, `identified_orders`, `unidentified_orders`, `total_orders` | Dataset identity, lifecycle, privacy-safe token verification and coverage counts |

Raw upload bytes are staged only during validation/import and are deleted when import finishes. Derived tables are
deleted with the dataset. Customer facts contain pseudonymous IDs only and are never returned as a customer list.

## Request flow

1. `POST /api/datasets` validates the multipart CSV, applies the row and cross-row rules, creates the DuckDB facts,
   stores only a SHA-256 token hash, and returns the dataset ID, one-time token, metadata and initial overview.
2. `require_dataset` validates the bearer header, dataset ID, file readability, expiry and token before a module
   handler runs. Authorization is performed before every request, including cache hits.
3. The handler resolves the inclusive active range and comparison mode, builds a cache key, and either returns a
   successful cached JSON body or opens the dataset read-only and computes the module response.
4. The response is aggregate-only JSON. The cache stores successful serialized bodies only, with a key containing
   dataset ID, module, active dates, comparison mode and module options.
5. Dataset expiry, explicit deletion and cleanup sweep invalidate the dataset's cache entries. The cache is process
   local, thread-safe, LRU-bounded, and expires entries at the earlier of its TTL and dataset expiry.

## API surface

All dataset routes require `Authorization: Bearer <token>` except the public health, config and sample-download
routes. The live OpenAPI schema is the authority; this table is checked against it by
`backend/tests/test_documentation.py`.

| Method | Path | Auth | Purpose and main options |
| --- | --- | --- | --- |
| GET | `/api/health` | No | Legacy health response |
| GET | `/health/live` | No | Process liveness only; no dependency checks |
| GET | `/health/ready` | No | Readiness and safe service identity |
| GET | `/api/config` | No | Public demo flag and upload limits; never secrets or paths |
| POST | `/api/datasets` | No | Multipart upload; `currency` form field |
| POST | `/api/datasets/sample` | No | Import the bundled sample in USD |
| GET | `/api/sample.csv` | No | Download the bundled sample CSV |
| GET | `/api/datasets/{id}` | Yes | Dataset metadata, capabilities, coverage and expiry |
| GET | `/api/datasets/{id}/analytics` | Yes | Legacy overview summary; optional `start`, `end` |
| DELETE | `/api/datasets/{id}` | Yes | Delete the dataset and invalidate its cache |
| GET | `/api/datasets/{id}/overview` | Yes | Overview KPIs and trend; `start`, `end`, `comparison` |
| GET | `/api/datasets/{id}/products` | Yes | Portfolio analytics; `start`, `end`, `comparison`, `dormancy_days` |
| GET | `/api/datasets/{id}/products/detail` | Yes | Product detail; `product_id`, `start`, `end`, `comparison` |
| GET | `/api/datasets/{id}/customers` | Yes | Customer aggregates and projection; `start`, `end`, `comparison` |

## Deployment shape

The Docker image builds the frontend in a Node stage, installs the backend environment with `uv`, and runs one
FastAPI process. FastAPI serves the built SPA and `/api` from port 8000. `DATASET_DIR` should be a private persistent
volume when datasets must survive a restart; there is no shared database or horizontal scaling layer.

