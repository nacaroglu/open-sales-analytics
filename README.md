# open-sales-analytics

Lightweight sales analytics: upload a completed-sales CSV, validate and analyse it with Python and DuckDB, and explore the results in a React/Recharts dashboard.

See [`_docs/plan.md`](_docs/plan.md) for the full specification and [`_docs/tasks.md`](_docs/tasks.md) for the implementation backlog.

## Development

```sh
uv sync
uv run pytest
```

Start the backend (serves on http://127.0.0.1:8000):

```sh
uv run uvicorn app.main:app --app-dir backend
```

Check it: `curl http://127.0.0.1:8000/api/health` returns `{"status":"ok"}`.

### Frontend

Requires Node 22 or newer. From `frontend/`:

```sh
npm ci            # install
npm run dev       # dev server on http://localhost:5173
npm test          # Vitest, single run
npm run typecheck # tsc --noEmit
npm run build     # writes frontend/dist
```

### Browser test

One Playwright test (Chromium) covers the happy path: load the sample, see the dashboard, change the date range.
Install the browser once (about 150 MB, stored outside the repository), then run it from `frontend/`:

```sh
npx playwright install chromium
npm run e2e
```

`npm run e2e` starts the backend (port 8000) and the Vite dev server (port 5173) itself, with a temporary dataset
directory, and stops them afterwards. Both ports must be free. To test an app that is already running (for example
the container), set `E2E_BASE_URL`; no server is started then:

```sh
E2E_BASE_URL=http://localhost:8000 npm run e2e
```

On failure a trace and a screenshot are saved in `frontend/test-results/` (open a trace with `npx playwright show-trace`).
