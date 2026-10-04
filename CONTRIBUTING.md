# Contributing

Thanks for looking. This is a small project; the notes below are the whole process.

## Set up

You need [uv](https://docs.astral.sh/uv/) and Node 22 or newer. From the repository root:

```sh
uv sync
(cd frontend && npm ci)
```

The [README](README.md#development) has the commands to start the backend and the dev server.

## Before a pull request

Run these from the repository root and from `frontend/`. CI runs the same checks.

```sh
uv run pytest
uv run ruff check backend
uv run ruff format --check backend
uv run mypy backend/app
```

```sh
cd frontend
npm test
npm run lint
npm run typecheck
npm run e2e   # needs Chromium once: npx playwright install chromium (see the README, "Browser test")
```

## Workflow

- One task is one GitHub issue, and one pull request closes one issue. Open or pick an issue first, and read its
  acceptance criteria before you start.
- Keep the change inside what the issue names. Commit regularly.
- Write tests for new behaviour; read [`_docs/testing-guidelines.md`](_docs/testing-guidelines.md) first. For anything
  that touches the UI, read [`_docs/design-system.md`](_docs/design-system.md).
- How work is organized here: [`_docs/process.md`](_docs/process.md).

## Dependencies

Ask before you add one. Open an issue that says what it is for and why the existing tools are not enough. Python
dependencies are declared in `pyproject.toml`.

## Report a problem

Use [GitHub issues](https://github.com/nacaroglu/open-sales-analytics/issues/new/choose); there is no other channel.
Pick the [bug report](.github/ISSUE_TEMPLATE/bug_report.yml) or the
[feature request](.github/ISSUE_TEMPLATE/feature_request.yml) form. Do not attach real customer data: use the sample
file or a small made-up CSV.
