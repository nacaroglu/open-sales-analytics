# アーキテクチャ

言語：[English](architecture.md) | [Türkçe](architecture.tr-TR.md) | [Deutsch](architecture.de-DE.md) | [Русский](architecture.ru-RU.md) | [Español](architecture.es-ES.md) | [简体中文](architecture.zh-CN.md) | [日本語](architecture.ja-JP.md)

> この翻訳は[英語の原文](architecture.md)を正とします。同期リビジョン `045796b0c7bbdd21520ccce1c7972495aab929f8`、同期日 `2026-10-22`。

Open Sales Analytics は、FastAPI が配信する同一オリジンの React/Vite アプリケーションです。フロントエンドはデータセット識別子と bearer トークンを一つのブラウザタブの `sessionStorage` に保持し、日付範囲と比較の選択をバックエンドへ送って集計レスポンスを描画します。バックエンドは、データセットごとの DuckDB ファイル一つと上限付きのプロセスローカルなレスポンスキャッシュを除き、リクエスト間でステートレスです。

## リポジトリのドメイン

| ドメイン | 実際のパス | 責務 |
| --- | --- | --- |
| API とライフサイクル | `backend/app/api/`, `backend/app/auth.py`, `backend/app/cleanup.py` | アップロード/サンプル作成、認可、有効期限、メタデータ、レスポンスエンベロープ |
| 概要 | `backend/app/analytics/overview/` | 総売上、個別注文数、販売個数、平均注文額、トレンド、比較 |
| 商品 | `backend/app/analytics/products/` | ランキング、シェア/Pareto、成長、休眠、価格履歴、注文浸透率、バスケット親和性 |
| 顧客 | `backend/app/analytics/customers/` | カバレッジ、顧客集計、コホート、RFM、予測 |
| 共通期間と可用性 | `backend/app/analytics/shared/` | 両端を含む日付フィルター、比較期間、バケット選択、可用性、指標定義 |
| インポートと永続化 | `backend/app/ingest.py`, `backend/app/importer.py`, `backend/app/schema.py` | CSV の検証、ファクト構築、データセットファイル書き込み、ステージングデータ削除 |
| Web UI | `frontend/src/` | アップロード、ダッシュボードナビゲーション、アクセシブルな状態、表、チャートの代替テキスト |

権威ある指標の式と状態は `backend/app/analytics/shared/metrics.py` にあり、人が読めるカタログは [_docs/metrics.md](metrics.ja-JP.md)です。フェーズ 3 の製品仕様は [_docs/open_sales_analytics_phase_3_spec.md](open_sales_analytics_phase_3_spec.md)です。

## データセットファイル

アップロードごとに `DATASET_DIR` 配下へ非公開の DuckDB ファイルが一つ作られます。インポート時に再利用可能なファクトを一度計算し、リクエスト時のクエリは選択された両端を含む範囲と比較期間でそのファクトを絞り込みます。

| テーブル | 列 | 意味 |
| --- | --- | --- |
| `line_items` | `order_id`, `order_date`, `product_id`, `product_name`, `quantity`, `unit_price`, nullable `customer_id` | 検証済みのソース行。商品明細ごとに一行で、任意の不透明な顧客 ID を含む |
| `order_facts` | `order_id`, `first_order_date`, `last_order_date`, `line_count`, `units`, `gross_sales` | 注文ごとに一行と、そのライフタイム明細/注文合計 |
| `product_facts` | `product_id`, `product_name`, `first_sale_date`, `last_sale_date`, `lifetime_gross_sales`, `lifetime_units`, `lifetime_orders` | 商品ごとに一行と、ライフタイムの商品ポートフォリオファクト |
| `customer_facts` | `customer_id`, `first_order_date`, `acquisition_month`, `first_day_orders`, `last_order_date`, `lifetime_orders`, `lifetime_units`, `lifetime_gross_sales` | 識別済み顧客ごとに一行。6 列データでは存在しないか空 |
| `dataset_meta` | `id`, `currency`, `created_at`, `expires_at`, `token_hash`, `row_count`, `has_customer_id`, `identified_orders`, `unidentified_orders`, `total_orders` | データセットの識別、ライフサイクル、プライバシーに配慮したトークン検証、カバレッジ件数 |

生のアップロードバイトは検証/インポート中だけステージングされ、インポート完了時に削除されます。派生テーブルはデータセットと共に削除されます。顧客ファクトには仮名化 ID だけが含まれ、顧客リストとして返されることはありません。

## リクエストフロー

1. `POST /api/datasets` は multipart CSV を検証し、行ルールと行間ルールを適用して DuckDB ファクトを作成し、SHA-256 トークンハッシュだけを保存して、データセット ID、一度だけ表示するトークン、メタデータ、初期概要を返します。
2. `require_dataset` はモジュールハンドラー実行前に bearer ヘッダー、データセット ID、ファイルの可読性、有効期限、トークンを検証します。キャッシュヒットを含むすべてのリクエストで認可を実施します。
3. ハンドラーは両端を含むアクティブ範囲と比較モードを解決し、キャッシュキーを構築して、成功済みのキャッシュ JSON 本文を返すか、データセットを読み取り専用で開いてモジュールレスポンスを計算します。
4. レスポンスは集計のみの JSON です。キャッシュは成功したシリアライズ済み本文だけを保存し、そのキーにはデータセット ID、モジュール、アクティブ日付、比較モード、モジュールオプションが含まれます。
5. データセットの期限切れ、明示的削除、クリーンアップスイープにより、そのデータセットのキャッシュエントリは無効になります。キャッシュはプロセスローカルでスレッドセーフ、LRU 上限付きで、TTL とデータセット有効期限の早い方でエントリが失効します。

## API サーフェス

公開のヘルス、設定、サンプルダウンロードルートを除くすべてのデータセットルートには `Authorization: Bearer <token>` が必要です。稼働中の OpenAPI スキーマが正であり、`backend/tests/test_documentation.py` がこの表と照合します。

| メソッド | パス | 認証 | 目的と主なオプション |
| --- | --- | --- | --- |
| GET | `/api/health` | 不要 | 旧ヘルス応答 |
| GET | `/health/live` | 不要 | プロセスの稼働のみ確認。依存関係は確認しない |
| GET | `/health/ready` | 不要 | 準備状態と安全なサービス識別情報 |
| GET | `/api/config` | 不要 | 公開デモフラグとアップロード制限。秘密やパスは含まない |
| POST | `/api/datasets` | 不要 | Multipart アップロード。`currency` フォームフィールド |
| POST | `/api/datasets/sample` | 不要 | 組み込みサンプルを USD でインポート |
| GET | `/api/sample.csv` | 不要 | 組み込みサンプル CSV をダウンロード |
| GET | `/api/datasets/{id}` | 必要 | データセットのメタデータ、機能、カバレッジ、有効期限 |
| GET | `/api/datasets/{id}/analytics` | 必要 | 旧式の概要サマリー。任意の `start`, `end` |
| DELETE | `/api/datasets/{id}` | 必要 | データセットを削除しキャッシュを無効化 |
| GET | `/api/datasets/{id}/overview` | 必要 | 概要 KPI とトレンド。`start`, `end`, `comparison` |
| GET | `/api/datasets/{id}/products` | 必要 | ポートフォリオ分析。`start`, `end`, `comparison`, `dormancy_days` |
| GET | `/api/datasets/{id}/products/detail` | 必要 | 商品詳細。`product_id`, `start`, `end`, `comparison` |
| GET | `/api/datasets/{id}/customers` | 必要 | 顧客集計と予測。`start`, `end`, `comparison` |

## デプロイ構成

Docker イメージは Node ステージでフロントエンドをビルドし、`uv` でバックエンド環境をインストールして、一つの FastAPI プロセスを実行します。FastAPI はポート 8000 からビルド済み SPA と `/api` を配信します。再起動後もデータセットを残す必要がある場合は、`DATASET_DIR` に非公開の永続ボリュームを使用してください。共有データベースや水平スケーリング層はありません。
