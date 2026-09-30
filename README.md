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
