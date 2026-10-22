# コントリビューションガイド

言語：[English](CONTRIBUTING.md) | [Türkçe](CONTRIBUTING.tr-TR.md) | [Deutsch](CONTRIBUTING.de-DE.md) | [Русский](CONTRIBUTING.ru-RU.md) | [Español](CONTRIBUTING.es-ES.md) | [简体中文](CONTRIBUTING.zh-CN.md) | [日本語](CONTRIBUTING.ja-JP.md)

> この翻訳は[英語の原文](CONTRIBUTING.md)を正とします。同期リビジョン `045796b0c7bbdd21520ccce1c7972495aab929f8`、同期日 `2026-10-22`。

Open Sales Analytics へのご協力ありがとうございます。バグ報告、アイデア、プルリクエストを歓迎します。

## バグ報告または機能リクエスト

**Bug report** または **Feature request** テンプレートを使って Issue を作成してください。バグの場合は、問題を再現する最小の CSV が最も役立ちます。実際の顧客データは絶対に添付せず、架空の注文 ID と顧客 ID を使用してください。セキュリティ上の問題は公開 Issue ではなく、Security タブの GitHub **Report a vulnerability** ボタンから非公開で報告してください。

## 作業の進め方

- 作業は GitHub Issue で一件ずつ追跡します。Issue には目標、受け入れ基準、対象外、制約を記載します（[`_docs/task-template.md`](_docs/task-template.md)）。
- `feature/issue-42-short-name` のように Issue にちなんだ名前のブランチで作業してください。`main` へ直接コミットしないでください。
- Issue ごとにプルリクエストを一つ作成します。レビューを終え、必須の CI チェックが通過した後にマージされます。

完全なプロセスは [`_docs/process.md`](_docs/process.md) にあります。

## セットアップ

[uv](https://docs.astral.sh/uv/) と Node 22 以降が必要です。

```sh
uv sync                    # backend and dev tools
(cd frontend && npm ci)    # frontend
```

バックエンドとフロントエンドの実行方法は README の[開発](README.ja-JP.md#開発)を参照してください。

## プルリクエストを作成する前に

CI が実行するチェックを実行してください。

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

ユーザージャーニーを変更した場合は、ブラウザテストも実行してください（`frontend/` で `npm run e2e`。詳細は[ブラウザテスト](README.ja-JP.md#ブラウザテスト)を参照）。

## ルール

- **テスト。** 新しい動作にはテストが必要です。最初に [`_docs/testing-guidelines.md`](_docs/testing-guidelines.md)を読んでください。
- **UI。** UI に関わるものはすべて [`_docs/design-system.md`](_docs/design-system.md)に従います。記載のないパターンは、同じ変更で同文書に追記してください。
- **依存関係。** 追加する前に Issue で許可を得てください。依存関係は `pyproject.toml` と `frontend/package.json` に宣言します。
- **用語。** 指標は「gross sales」（総売上）であり、「revenue」（収益）とは呼びません。
- **プライバシー。** トークン、ファイル内容、顧客 ID をログに記録したり表示したりしてはいけません（[プライバシー](README.ja-JP.md#プライバシー)を参照）。

## ライセンス

コントリビューションを行うことにより、そのコントリビューションが [Apache License 2.0](LICENSE) の下でライセンスされることに同意したものとみなされます。
