# Contributing

Languages: [English](CONTRIBUTING.md) | [Türkçe](CONTRIBUTING.tr-TR.md) | [Deutsch](CONTRIBUTING.de-DE.md) | [Русский](CONTRIBUTING.ru-RU.md) | [Español](CONTRIBUTING.es-ES.md) | [简体中文](CONTRIBUTING.zh-CN.md) | [日本語](CONTRIBUTING.ja-JP.md)

Thanks for helping with Open Sales Analytics. Bug reports, ideas and pull requests are all welcome.

## Reporting a bug or asking for a feature

Open an issue with the **Bug report** or **Feature request** template. For a bug, the smallest CSV that shows it
helps most. Never attach real customer data: use made-up order and customer IDs. Report a security problem privately
through GitHub's **Report a vulnerability** button on the Security tab, not in a public issue.

## How work is organized

- Work is tracked as GitHub issues, one at a time. An issue states its goal, acceptance criteria, what is out of
  scope and its constraints ([`_docs/task-template.md`](_docs/task-template.md)).
- Work on a branch named after the issue, for example `feature/issue-42-short-name`. Never commit to `main`.
- One pull request per issue. It is merged after review and once the required CI checks pass.

The full process is in [`_docs/process.md`](_docs/process.md).

## Setting up

You need [uv](https://docs.astral.sh/uv/) and Node 22 or newer.

```sh
uv sync                    # backend and dev tools
(cd frontend && npm ci)    # frontend
```

[Development](README.md#development) in the README explains how to run the backend and the frontend.

## Before you open a pull request

Run the checks CI runs:

```sh
uv run pytest
uv run ruff check backend
uv run ruff format --check backend
uv run mypy backend/app
cd frontend
npm test
npm run lint
npm run typecheck
npm run build
```

For a change to a user journey, also run the browser tests (`npm run e2e` in `frontend/`, see
[Browser test](README.md#browser-test)).

## Rules

- **Tests.** New behaviour comes with tests. Read [`_docs/testing-guidelines.md`](_docs/testing-guidelines.md) first.
- **UI.** Anything that touches the UI follows [`_docs/design-system.md`](_docs/design-system.md). A pattern it does not
  cover gets a line there in the same change.
- **Dependencies.** Ask in the issue before you add one. Dependencies are declared in `pyproject.toml` and
  `frontend/package.json`.
- **Wording.** The measure is "gross sales", never "revenue".
- **Privacy.** Nothing may log or display tokens, file contents or customer IDs (see
  [Privacy](README.md#privacy)).

## License

By contributing, you agree that your contributions are licensed under the [Apache License 2.0](LICENSE).
