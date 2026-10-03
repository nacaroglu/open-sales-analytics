# Testing guidelines

How tests are written here today. Read before writing a test. If the repo differs, fix this file in the same change.

## Where tests live, how to run them

Backend: `backend/tests/test_<area>.py`, flat. No `conftest.py`, no markers, no subfolder except
`backend/tests/fixtures/`, so a fixture is defined in the test file that uses it. Test names are a sentence about
the behaviour (`test_expired_dataset_is_404_even_with_correct_token`). Run from the repository root (settings in `pyproject.toml`):

- `uv run pytest` (all), `uv run pytest backend/tests/test_health.py` (one file),
  `uv run pytest backend/tests/test_health.py::test_health_returns_ok` (one test)

Frontend: `frontend/src/**/<name>.test.ts` or `.test.tsx` next to the code (Vitest, jsdom). From `frontend/`:
`npm test` (all, single run), `npx vitest run src/App.test.tsx` (one file), `npm run lint`, `npm run typecheck`, `npm run build`.

CI (`.github/workflows/ci.yml`) runs pytest, `ruff check`, `ruff format --check`, `mypy backend/app`, and in `frontend/` `npm test`, `npm run lint`,
`npm run typecheck`, then the browser suite on the built container.
Baseline, measured 2026-09-30: `uv run pytest` 632 tests in about 50 s; `npm test` 308 tests in about 9 s (re-measured 2026-10-04 in #46).

## Levels (plan section 12)

- Unit: a function called directly on a small hand-built dataset or CSV (`test_kpis.py`, `test_validation_rows.py`).
  Vitest component and hook tests are unit level and never start the backend.
- Integration: a request through `TestClient(app)` with settings overridden (`test_upload_endpoint.py`,
  `test_analytics_endpoint.py`). A real `uvicorn` subprocess only for what an in-process client cannot
  see: startup failure and log output on the real stream (`test_startup.py`, `test_logging.py`).
- Browser: a small suite of journeys (Playwright, Chromium, `frontend/e2e/*.spec.ts`, `npm run e2e`; CI runs all of it on the
  container). One spec per journey, selectors by role or label, CSVs written inline (`e2e/helpers.ts`), no fixed sleeps.
  `npm run e2e` starts its own backend and Vite on a temporary `DATASET_DIR`; with `E2E_BASE_URL` it tests a running app
  instead. Expiry cannot be configured on a container (the TTL is whole hours), so `lifecycle.spec.ts` serves the server's
  own 404 `not_found` answer to a real, open dataset; the backend tests cover the real expiry. No browser test beyond the journeys.

Plan section 12 rules and their tests: validation rules `test_validation_structure.py`, `_rows.py`,
`_cross_row.py`; metrics, granularity, date boundaries `test_kpis.py`, `test_top_products.py`,
`test_trend.py`; token verification and expiry `test_tokens.py`, `test_auth.py`; upload and
"rejected upload leaves nothing" `test_upload_endpoint.py`; filtered analytics
`test_analytics_endpoint.py`; missing or invalid token `test_auth.py`, `test_delete_endpoint.py`,
`test_metadata_endpoint.py`; expired inaccessible and cleaned up `test_auth.py`, `test_cleanup.py`;
demo mode `test_demo_mode.py`; the browser journeys `frontend/e2e/*.spec.ts` (`happy-path`, `upload`, `dashboard`, `lifecycle`).

## Isolation and settings
Tests never read or write the real `DATASET_DIR` (default `./tmp_datasets`). Two patterns:

- (a) `Settings(DATASET_DIR=tmp_path / "data", ...)` plus `app.dependency_overrides[get_settings] = lambda: settings`
  in a fixture, `app.dependency_overrides.clear()` after the `yield` (`test_upload_endpoint.py`). Use for endpoint and service tests.
- (b) `monkeypatch.setenv(...)` with `get_settings.cache_clear()` before and after, because
  `get_settings` is cached (`test_config.py`, `test_startup.py`). Use only when the test is about reading the environment.

Files go under `tmp_path` (pytest removes it); leave nothing in the repo. `TestClient(app)` without `with` does not
run the startup sweep and timer; `with TestClient(app):` does (`test_cleanup.py`, lifespan section): use it only when
the test is about startup. A subprocess test passes an explicit `env` dict (`PATH` plus only what it needs), never the
developer's environment, and terminates and waits for the process in a `finally` (`test_logging.py`).

## Time

Never sleep for expiry or for "today" to change. Handles: the `get_now` dependency in `app.auth`
(`app.dependency_overrides[get_now] = lambda: fixed`); `now=` on `sweep` and the importer; `today=` on the
row validator; `sleep=` on `run_cleanup_loop`. Use a fixed `datetime(..., tzinfo=UTC)`. Test exactly at the
limit and one second either side: `test_cleanup.py::test_expiry_exactly_now_is_expired_one_second_later_is_not`,
`test_auth.py::test_one_second_before_expiry_is_accepted`,
`test_validation_rows.py::test_today_is_accepted_and_tomorrow_is_the_future`.
The one accepted real wait is a bounded poll (100 tries, 0.1 s apart) until a spawned server answers
`/api/health`, in `test_logging.py`. Any new wait must be bounded and poll a condition, never a fixed sleep.

## Fixtures

CSVs live in `backend/tests/fixtures/<group>/<name>.csv` (groups: `rows/`, `cross_row/`) and are loaded with
`Path(__file__).parent / "fixtures" / "<group>"`. Named after the rule, one violation per file. Clean files:
`rows/clean.csv` and `cross_row/clean_multi_line_orders.csv` (no `cross_row/clean.csv`). The one file with several
violations is `cross_row/all_rules_together.csv`, on purpose.
A single-use CSV is written inline (`HEADER` plus rows, under `tmp_path`). `backend/app/sample/sample_sales.csv`
is application data, not a fixture. Frontend tests build data inline (objects typed with `frontend/src/lib/types.ts`,
`File` objects for uploads); there is no frontend fixtures folder.

## Logging and secrets

Assert log output from JSON lines read via `capsys` (the `log` fixture in `test_logging.py`), or `caplog`
with `logger="app"` for demo-mode records (`test_demo_mode.py`). A test that touches tokens, hashes or
uploaded content asserts none of them appear in the captured output
(`test_successful_upload_leaves_no_marker_or_token_in_the_log`, `test_token_hash_never_reaches_the_log`).

## Frontend patterns

Stub fetch (`api.test.ts`, `hooks.test.tsx`): `vi.stubGlobal("fetch", fetchMock)` in `beforeEach`;
`fetchMock.mockReset()`, `vi.unstubAllGlobals()`, `window.sessionStorage.clear()` in `afterEach`; respond with
`new Response(JSON.stringify(body), { status })`; assert on the URL and `Authorization` header of `fetchMock.mock.calls`.
Hook and component tests wrap in `QueryClientProvider` with a fresh `new QueryClient({ defaultOptions:
{ queries: { retry: false } } })` per test, wait with `waitFor` / `findBy...` (never sleep), and use `fireEvent`:
`@testing-library/user-event` and MSW are not installed (adding one needs approval, see `AGENTS.md`).
`src/test-setup.ts` loads the `@testing-library/jest-dom` matchers.

jsdom caveats (when you hit a new one, add it here in one line):

- No layout, no `ResizeObserver`: Recharts' `ResponsiveContainer` renders nothing unless the test stubs
  `ResizeObserver` and sizes the container. The stub is in `frontend/src/test-setup.ts` (reports a fixed 800 x 288 px
  box on `observe`), so charts render in every test without further setup.
- Abort errors: in jsdom `new DOMException("x", "AbortError") instanceof Error` is false (verified 2026-09-30), so
  `fetchMock.mockRejectedValue(new DOMException(...))` is not an `Error`; `signal.reason` after `controller.abort()`
  and a real `fetch` rejected by an aborted signal are `instanceof Error`. `isAbort` (`frontend/src/lib/api.ts`) is
  true when `signal.aborted` or (`instanceof Error` and name `AbortError`): pass a signal, abort it, assert on `signal.aborted`.

## Fast and clean
No network, no fixed sleeps, small hand-built datasets, no shared state: each test gets its own `tmp_path`,
`QueryClient` and stubs. A test that leaves a server, a file or a stubbed global behind is a bug.
