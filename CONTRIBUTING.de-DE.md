# Mitwirken

[English](CONTRIBUTING.md) | [Türkçe](CONTRIBUTING.tr-TR.md) | [Deutsch](CONTRIBUTING.de-DE.md) | [Русский](CONTRIBUTING.ru-RU.md) | [Español](CONTRIBUTING.es-ES.md) | [简体中文](CONTRIBUTING.zh-CN.md) | [日本語](CONTRIBUTING.ja-JP.md)

> Maßgeblich für die Richtigkeit dieser Übersetzung ist das [englische Dokument](CONTRIBUTING.md). Synchronisierungsrevision: `045796b0c7bbdd21520ccce1c7972495aab929f8` (2026-10-22).

Vielen Dank für deine Hilfe bei Open Sales Analytics. Fehlerberichte, Ideen und Pull Requests sind willkommen.

## Einen Fehler melden oder eine Funktion vorschlagen

Eröffne ein Issue mit der Vorlage **Bug report** oder **Feature request**. Bei einem Fehler hilft eine möglichst kleine
CSV-Datei, die ihn reproduziert, am meisten. Hänge niemals echte Kundendaten an: Verwende erfundene Bestell- und
Kunden-IDs. Melde ein Sicherheitsproblem vertraulich über GitHubs Schaltfläche **Report a vulnerability** im Tab
Security und nicht in einem öffentlichen Issue.

## Wie die Arbeit organisiert ist

- Die Arbeit wird einzeln in GitHub-Issues verfolgt. Ein Issue nennt Ziel, Akzeptanzkriterien, ausgeschlossene Inhalte
  und Einschränkungen ([`_docs/task-template.md`](_docs/task-template.md)).
- Arbeite in einem nach dem Issue benannten Branch, zum Beispiel `feature/issue-42-short-name`. Committe niemals auf `main`.
- Ein Pull Request pro Issue. Er wird nach der Prüfung und nach erfolgreichem Abschluss aller erforderlichen CI-Checks
  zusammengeführt.

Der vollständige Prozess steht in [`_docs/process.md`](_docs/process.md).

## Einrichtung

Du benötigst [uv](https://docs.astral.sh/uv/) sowie Node 22 oder neuer.

```sh
uv sync                    # backend and dev tools
(cd frontend && npm ci)    # frontend
```

[Entwicklung](README.de-DE.md#entwicklung) in der README erklärt, wie Backend und Frontend gestartet werden.

## Vor dem Öffnen eines Pull Requests

Führe die Checks aus, die auch CI ausführt:

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

Führe bei einer Änderung an einem Benutzerablauf auch die Browser-Tests aus (`npm run e2e` in `frontend/`; siehe
[Browser-Test](README.de-DE.md#browser-test)).

## Regeln

- **Tests.** Neues Verhalten wird mit Tests geliefert. Lies zuerst
  [`_docs/testing-guidelines.md`](_docs/testing-guidelines.md).
- **UI.** Alles, was die UI betrifft, folgt [`_docs/design-system.md`](_docs/design-system.md). Ein dort nicht
  abgedecktes Muster wird mit derselben Änderung als Zeile ergänzt.
- **Abhängigkeiten.** Frage im Issue, bevor du eine hinzufügst. Abhängigkeiten werden in `pyproject.toml` und
  `frontend/package.json` deklariert.
- **Wortwahl.** Die Kennzahl heißt „gross sales“, niemals „revenue“.
- **Datenschutz.** Nichts darf Tokens, Dateiinhalte oder Kunden-IDs protokollieren oder anzeigen (siehe
  [Datenschutz](README.de-DE.md#datenschutz)).

## Lizenz

Mit deinem Beitrag stimmst du zu, dass deine Beiträge unter der [Apache License 2.0](LICENSE) lizenziert werden.
