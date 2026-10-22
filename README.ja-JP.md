# open-sales-analytics

言語：[English](README.md) | [Türkçe](README.tr-TR.md) | [Deutsch](README.de-DE.md) | [Русский](README.ru-RU.md) | [Español](README.es-ES.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja-JP.md)

> この翻訳は[英語の原文](README.md)を正とします。同期リビジョン `045796b0c7bbdd21520ccce1c7972495aab929f8`、同期日 `2026-10-22`。

Open Sales Analytics は小規模なセルフホスト型 Web アプリケーションです。完了した販売明細の CSV をアップロードすると、総売上、注文数、販売個数、平均注文額、販売トレンド、上位商品が表示され、日付範囲も変更できます。総売上は、選択期間内の各明細について数量と単価を掛けた値の合計で、返金、値引き、税、送料は含みません。

目次：[Docker で実行](#docker-で実行) | [設定](#設定) | [デモ手順](#デモ手順) | [結果を確認](#6-結果を確認) | [商品分析](#商品分析) | [顧客分析](#顧客分析) | [比較](#比較) | [データセット契約](#データセット契約) | [通貨](#通貨) | [プライバシー](#プライバシー) | [デモモード](#デモモード) | [制限](#制限) | [ロードマップ](#ロードマップ) | [アーキテクチャ](#アーキテクチャ) | [開発](#開発) | [コントリビューション](#コントリビューション) | [ライセンス](#ライセンス)

## Docker で実行

公開済みイメージはないため、このリポジトリをチェックアウトして一度ビルドしてから実行します。

```sh
docker build -t open-sales-analytics .
docker run -p 8000:8000 open-sales-analytics
```

<http://localhost:8000> を開きます。アップロード画面が表示され、**Try sample data** でサンプルファイルのダッシュボードが開きます。`curl http://localhost:8000/api/health` は `{"status":"ok"}` を返します。

コンテナは非 root ユーザー（UID 10001）で動き、データセットを `/data`（`DATASET_DIR=/data`）に保存します。ボリュームがなければ、コンテナ削除時に失われます。保持するには名前付きボリュームを `/data` にマウントします。

```sh
docker run -p 8000:8000 -v osa-data:/data open-sales-analytics
```

ボリュームを使うと、データセットはベストエフォートで `docker restart` とコンテナ再作成を越えて残りますが、それぞれ `DATASET_TTL_HOURS` 後に失効します。名前付きボリュームの代わりにホストディレクトリを `/data` へマウントする場合、コンテナの非 root ユーザー（UID 10001）が書き込める必要があります。例：`sudo chown 10001 /path/to/dir`。

イメージは自己診断します。起動数秒後に `docker ps` は `healthy` を表示し、`/api/health` が応答しなくなると `unhealthy` になります（10 秒ごと、タイムアウト 3 秒、3 回失敗、開始猶予 10 秒）。`docker stop` はバックグラウンドのクリーンアップを止めた後、1 秒未満で終了コード 0 によりサーバーを終了します。サーバー自身はリクエストタイムアウトを設けず（uvicorn のデフォルト）、非常に遅いアップロードはクライアントが断念した時点で終了します。

[下表](#設定)の変数を `-e` で渡します。

```sh
docker run -p 8000:8000 -e PUBLIC_DEMO_MODE=true open-sales-analytics
```

## デモ手順

生成サンプルデータを使い、新規チェックアウトからダッシュボードまで進む手順です。手順 1 は [uv](https://docs.astral.sh/uv/)、それ以外は Docker だけが必要です。

### 1. サンプルデータを生成

```bash
uv run python backend/scripts/generate_sample.py
```

`backend/app/sample/sample_sales.csv` が書き込まれます。シードによりファイルは決定的なので、誰が実行しても同じデータと手順 6 の同じ数値を得ます。ファイルはイメージへコピーされるため、`docker build` より先に実行してください。

先頭行を確認します。

```bash
head -n 4 backend/app/sample/sample_sales.csv
```

```
order_id,order_date,product_id,product_name,quantity,unit_price,customer_id
ORD-000001,2024-01-01,P001,Ceramic Mug,1,12.00,CUST-6ebe7ed43ba4
ORD-000001,2024-01-01,P002,Travel Tumbler,1,24.00,CUST-6ebe7ed43ba4
ORD-000002,2024-01-01,P001,Ceramic Mug,1,12.00,CUST-c4da5c3ce3f2
```

### 2. イメージをビルド

```bash
docker build -t open-sales-analytics .
```

### 3. コンテナを実行

```bash
docker run -p 8000:8000 open-sales-analytics
```

ログに `Uvicorn running on http://0.0.0.0:8000` と出れば準備完了です。

### 4. Web インターフェースを開く

<http://localhost:8000> を開きます。アップロード画面にファイル形式とアップロードフォームが表示されます。

### 5. サンプルデータをアップロード

`backend/app/sample/sample_sales.csv` を選び、**USD** を選択して **Upload** をクリックします。（**Try sample data** はファイル選択なしで同じファイルをインポートします。）

![サンプルファイルと USD を選択したアップロードフォーム](_docs/images/demo-upload.png)

### 6. 結果を確認

ダッシュボードは**概要**を開き、データの全期間 2024-01-01～2025-12-31 を表示します。

| 指標 | 期待値 |
| --- | --- |
| 行数 | 14,397 |
| 総売上 | $675,816.70 |
| 注文数 | 10,000 |
| 販売個数 | 24,380 |
| 平均注文額 | $67.58 |

![概要：主要数値、月次総売上トレンド、上位 10 商品](_docs/images/phase-3/overview.png)

全期間は 24 か月なのでトレンドは月次です（[トレンドバケット](#トレンドバケット)参照）。**開始日**と**終了日**を変えると全数値が絞り込まれ、**リセット**で全期間に戻ります。**比較対象**で前期間または前年同期を追加できます。データが 2024-01-01 に始まるため、全期間では比較できません。

**商品**には、ランキング、累積 Pareto チャート付き総売上シェア、上昇/下降商品、休眠商品、併買商品が表示されます。ここでは 2025 年を 2024 年と比較しています（[商品分析](#商品分析)参照）。

![商品：ランキング、Pareto チャート、上昇/下降商品、休眠、商品ペア](_docs/images/phase-3/products.png)

商品名を開くと、総売上トレンド、実際の平均単価、注文浸透率、併買商品を確認できます。

![商品詳細：総売上トレンド、加重単価、注文浸透率、関連商品](_docs/images/phase-3/product-detail.png)

**顧客**には、カバレッジ、顧客主要指標、購入間隔日数、コホート継続率ヒートマップ、過去顧客価値、予測 12 か月顧客価値、RFM セグメント、購入頻度、集中度が表示されます（[顧客分析](#顧客分析)参照）。

![顧客：カバレッジ、主要数値、コホート継続率ヒートマップ、価値、RFM、頻度、集中度](_docs/images/phase-3/customers.png)

**別のファイルを分析**すると、このデータセットを削除してアップロード画面へ戻ります。

## 比較

日付範囲カードでは、アクティブ範囲を前期間または前年同期と比較できます。ダッシュボードは API が返す正確な日付を表示します。比較がデータセットの最初の日より前に始まる場合、全範囲比較は利用できません。閏日の比較では比較年の 2 月の最終有効日を使います。以前の値がなければ「以前の値なし」、両方ゼロなら「変化なし」、新商品なら「新規」、それ以外の百分率は「比較可能」と表示します。

## 商品分析

特記しない限り、すべての商品数値は選択された両端を含むアクティブ範囲を使います。金額は総売上で、値引き、返金、原価はデータセット契約外です。商品名と ID はサーバー提供テキストとして表示します。

| UI ラベルとキー | 式と分母 | ウィンドウと通常外状態 | 計算例 |
| --- | --- | --- | --- |
| ランキング — `gross_sales` | 数量 × 単価の合計。販売個数は数量合計、注文は個別注文数 | アクティブ範囲。空範囲では商品なし | 単価 12.50 を 2 個の明細は総売上 25.00 |
| 総売上シェア — `gross_sales_share` | 商品総売上 / 全商品総売上 | アクティブ範囲。総売上ゼロはデータ不足 | 100 のうち 15 は 15.00% |
| 上位 20% シェア — `top_20_percent_share` | 商品数上位 20% の総売上 / 総売上 | アクティブ範囲。合計ゼロはデータ不足 | 50/20/15/10/5 の 5 商品では上位 1 商品が 50.00% |
| 80% 到達商品数 — `products_to_80_percent` | 累積シェアが 80% に達する最小の順序付き商品数 | アクティブ範囲。合計ゼロはデータ不足 | 50+20+15 は 3 商品で 80% に到達 |
| 累積シェア — `cumulative_share` | 累積総売上 / 総売上 | アクティブ範囲。合計ゼロは利用不可 | 先頭 3 黄金商品で 85.00% |
| 商品成長 — `product_growth` | 現在総売上－比較総売上。百分率は比較値を使用 | 比較期間。`新規`、`現在の売上なし`、`変化なし`、比較利用不可では誤解を招く百分率を避ける | 10 から 20 は +10、+100.00% |
| 上昇/下降ランキング — `rising_products`, `falling_products` | 総売上の絶対変化で順位付け | 選択比較。比較利用不可なら利用不可 | +10 の変化は +1（+900%）より上位 |
| 休眠商品 — `dormancy` | 選択した 30、60、90 日ウィンドウに販売がない商品。以前の合計はウィンドウ前販売を使用 | 選択範囲終了日（全範囲ならデータセット最新日）をアンカー、既定 60。履歴不足とゼロ結果は別。アンカーのちょうど N 日前はウィンドウ内 | 最終販売がアンカーの 60 日前なら 60 日ウィンドウに含む |
| 加重単価 — `weighted_unit_price` | SUM(quantity × unit price) / SUM(quantity) | アクティブ範囲バケット。販売なしバケットは欠損でゼロ価格ではない | 10 で 1 個、20 で 3 個なら 17.50 |
| 注文浸透率 — `order_penetration` | 商品を含む個別注文 / 全個別注文 | アクティブ範囲。注文ゼロはゼロ結果 | 200 注文中 25 は 12.50% |
| 支持度 — `basket_support` | 共通注文 / 対象バスケット注文 | アクティブ範囲。共通注文 10 件以上、支持度 0.1% が必要 | 10,000 注文中 10 件は 0.10% |
| 確信度 — `basket_confidence` | 共通注文 / 方向の起点商品を含む注文 | アクティブ範囲。しきい値未満ペアは非表示 | 注文数が違うため A→B と B→A は異なり得る |
| リフト — `basket_lift` | 確信度 / 宛先商品の支持度 | アクティブ範囲。しきい値未満ペアは非表示 | 観測ペア率を宛先支持度と比較 |

共通レジストリでは、これらのキーを Gross-sales share、Cumulative gross-sales share、Top 20% product share、Products to 80% of gross sales、Product gross-sales growth、Rising products、Falling products、Dormant products、Weighted realized unit price、Order penetration、Basket support、Basket confidence、Basket lift と表記します。

どちらかのバスケットしきい値未満のペアは、リフトが高くても表示しません。異なる商品が 100 を超える注文はバスケット分析からだけ除外します。ちょうど 100 は含み、その注文はランキング、浸透率、総売上には引き続き数えます。商品ビューには除外数を表示します。価格履歴は実現価格の動きだけを示し、価格弾力性や価格変化が販売変化を起こしたことは示しません。上昇/下降は小さな基準値が支配しないよう絶対変化を使います。浸透率、支持度、確信度、リフトは個別注文を使います。

API 文書は [`/docs`](http://localhost:8000/docs) にあります。`GET /api/datasets/{id}/overview` は概要 KPI とトレンド、`GET /api/datasets/{id}/products` はポートフォリオ分析、`GET /api/datasets/{id}/products/detail?product_id=...` は一商品の詳細分析を返します。データセットエンドポイントには、そのデータセットの bearer トークンが必要です。

## 顧客分析

顧客分析は集計のみです。識別済み注文を説明し、顧客識別子、顧客一覧、顧客別金額は決して表示しません。明示的に選択終了日までの全履歴と説明する行を除き、アクティブな報告範囲は開始日と終了日の両方を含みます。以下の計算値はコミット済み `backend/tests/fixtures/customers/golden_customers.csv` フィクスチャを使用します。2025-01-01～2025-09-30 に 20 注文、識別済み 19 注文、10 顧客、識別済み総売上 380.0000 です。

| UI ラベルとキー | 式、ウィンドウ、アンカー | データ不足とゼロ結果 | 計算例 |
| --- | --- | --- | --- |
| 顧客カバレッジ — `customer_coverage` | 識別済み個別注文 / 全個別注文。注文単位でデータセットと選択範囲を計数 | `customer_id` 列なしは利用不可、50% 未満は抑制、注文なしは null カバレッジ | 黄金フィクスチャで 19 / 20 = 95.0% |
| 識別済み顧客 — `identified_customers` | アクティブ範囲に識別済み明細がある個別 `customer_id`。範囲両端を含む | 識別済み顧客なしは `zero_result` で 0 | 黄金範囲は 10 |
| 新規対リピーター顧客総売上 — `new_vs_returning` | 各明細が顧客の全履歴初回注文日か後日かで `SUM(quantity × unit_price)` を分割。履歴は範囲終了まで | 識別済み行なしは `zero_result` で金額ゼロ | CUST-01 の 2024-12-15 購入により 2025 年販売はリピーター |
| リピート購入率 — `repeat_purchase` | 選択終了までに個別注文 2 件以上のアクティブ顧客 / アクティブ識別済み顧客。範囲開始前注文も数える | アクティブ顧客なしは `insufficient_data`、リピートなしは正確に 0（`zero_result`） | 同日注文は別注文であり別日ではない |
| 購入間隔日数 — `days_between_purchases` | 連続する個別注文間の暦日中央値。後の注文が範囲内なら含み、同日注文は 0 | 間隔なしは中央値 null と `insufficient_data`。固定バケット 0、1-7、8-14、15-30、31-60、61-90、91-180、181-365、366+ | 同日ペアはバケット 0 |
| コホート継続率 — `cohort_retention` | 暦月オフセットごとの継続顧客 / 全履歴獲得コホートサイズ。選択終了までの全履歴を使用 | コホートなしは `insufficient_data`。右端セルは `未観測` で 0% ではない | 非空コホートの月 0 は 100.0% |
| 過去顧客価値 — `historical_customer_value` | 終了日までの観測識別総売上 / 識別済み顧客数。中央値は顧客別価値の中央、コホート曲線は累積売上 | コホートなしは `insufficient_data`。観測売上ゼロはゼロ結果。予測ではない | 黄金フィクスチャは 10 顧客で 380.0000 |
| RFM セグメント — `rfm` | 最終購入は選択終了日前の日数、頻度は個別注文、金額は識別総売上。各次元は相対五分位、FM = F + M | 5 顧客未満は `insufficient_data`。同値は同スコア、完全な変換表はレジストリ内 | このアップロード相対で普遍的基準ではない |
| RFM セグメント詳細 — `rfm_drilldown` | セグメント総売上、固定最終購入バケット（0-30～366+）、頻度バケット（1、2、3、4、5、6-10、11-20、21+）。顧客別行なし | 5 顧客未満は `insufficient_data`。総売上ゼロはシェア null | 黄金フィクスチャは ID タイブレークなしの同値を含む |
| 購入頻度 — `purchase_frequency` | 選択終了までの識別済み個別注文数で顧客を 1、2、3、4、5、6-10、11-20、21+ に分類 | 識別済み顧客なしは空件数、null シェア、`insufficient_data` | 2 注文の顧客はバケット 2 |
| 顧客集中度 — `concentration` | 上位十分位総売上 / 識別総売上。N 顧客では範囲売上上位 `ceil(N / 10)` 人、境界同値のタイブレークなし | 10 顧客未満または識別総売上ゼロは `insufficient_data`、シェア null | N=10、売上 1000、500、100×8 なら 1000 / 2300 = 0.4348 |

50% と 80% のカバレッジ階層は次のように境界を含みます。50% 未満は非表示、50.0% 以上 80% 未満は低カバレッジ警告、80% 以上は正常です。UI は表示率を小数 1 桁で切り捨て、丸めで境界を越えません。カバレッジは明細単位でなく注文単位です。列なしは 0% ではなく利用不可です。

顧客識別とコホートは選択終了日までの全履歴を使います。開始日を遅らせても顧客を新規に再分類せず、コホート所属も変わりません。RFM 最終購入とコホート成熟度は今日でなく選択終了日にアンカーします。部分または未来コホートセルは**未観測**で、ゼロ結果ではありません。

アップロード整合性ルールは厳密です。注文内の空欄は唯一の非空 ID で補完し、異なる 2 ID はアップロード全体を拒否し、全空欄注文は未識別のままです。`customer_id` の既定上限は 128 文字です。ベストエフォート検査は明白なメール、電話、上限超過を拒否しますが、氏名、住所、国民 ID、可逆エンコード、珍しい電話形式は識別できません。

顧客データは仮名化であり匿名ではありません。UUID、内部キー、またはファイル外に秘密のソルトを置くハッシュを使ってください。レスポンスは集計件数と合計のみで、顧客一覧、検索、ダウンロード、エクスポートはなく、顧客 ID、コホート所属、RFM レコードはログに残しません。顧客データはデータセット DuckDB ファイルだけにあり、`DATASET_TTL_HOURS`（既定 24）後にファイルと共に、または**別のファイルを分析**ですぐ削除され、生 CSV はインポート後に削除されます。予測 12 か月顧客価値は将来の別指標で、この観測尺度ではありません。

## 設定

サーバーは起動時に次の環境変数を読みます。すべて任意です。

| 変数 | 型 | 既定値 | 効果 |
| --- | --- | --- | --- |
| `DATASET_DIR` | パス | `./tmp_datasets`（Docker イメージでは `/data`） | データセットごとの DuckDB ファイルを置くディレクトリ。なければ非公開権限で作成。 |
| `DATASET_TTL_HOURS` | 0 より大きい整数 | `24` | データセットが失効し削除されるまでの時間。 |
| `DATASET_TTL_SECONDS` | 0 より大きい整数 | 未設定 | テスト専用。設定時は `DATASET_TTL_HOURS` の代わりに秒単位寿命。ブラウザテストで実失効を確認し、本番では未設定にする。 |
| `MAX_UPLOAD_BYTES` | 0 より大きい整数 | `52428800`（50 MB） | 最大アップロードバイト数。超過は `file_too_large` で拒否。 |
| `MAX_ROWS` | 0 より大きい整数 | `500000` | 一アップロードの最大データ行数（ヘッダー除外）。超過は `too_many_rows`。 |
| `CUSTOMER_ID_MAX_LENGTH` | 0 より大きい整数 | `128` | 非空 `customer_id` の最大 Unicode 文字数。超過は `customer_id_too_long`。 |
| `CLEANUP_INTERVAL_MINUTES` | 0 より大きい整数 | `15` | 期限切れデータセット削除間隔（起動時にも一度実行）。 |
| `PUBLIC_DEMO_MODE` | 真偽値 | `false` | `true` でアップロード無効。[デモモード](#デモモード)参照。 |
| `MAX_DATASETS` | 0 より大きい整数 | `200` | 未失効データセット上限。さらに作成（アップロードまたは **Try sample data**）すると失効/削除まで 503 `capacity_reached`。 |
| `RESPONSE_CACHE_MAX_ENTRIES` | 0 以上の整数 | `256` | このプロセスの概要/商品レスポンスキャッシュ上限。`0` で無効。 |
| `RESPONSE_CACHE_TTL_SECONDS` | 0 より大きい整数 | `300` | 概要/商品キャッシュの最長寿命。データセット失効が常に優先。 |

真偽値は大文字小文字を問わず `true`/`false`、`1`/`0`、`yes`/`no`（`on`/`off`、`t`/`f`、`y`/`n` も可）を受け付けます。

無効値ではサーバーが起動を拒否し、エラーに変数名を示します。数字でない値、ゼロ/負数、`1.5` のような小数、空文字列、上記以外の真偽値表記が無効です。例：`MAX_ROWS=0 uv run uvicorn app.main:app --app-dir backend` は `MAX_ROWS  Input should be greater than 0` で終了します。

## データセット契約

一行は完了済み注文内の商品明細一つです。ファイルには次の必須 6 列と任意 1 列が必要です（アップロード画面にも同じ表を表示）。`customer_id` の意味とプライバシー制限は[顧客分析](#顧客分析)を参照してください。

| 列 | 型 | ルール |
| --- | --- | --- |
| `order_id` | 文字列 | 必須、非空。個別注文の計数に使用。 |
| `order_date` | 日付 | `YYYY-MM-DD` 形式の ISO 暦日が必須。未来日は不可。 |
| `product_id` | 文字列 | 必須、非空。商品を識別。 |
| `product_name` | 文字列 | 必須、非空。一アップロード内で一つの `product_id` は一つの名前だけに対応。 |
| `quantity` | 整数 | 必須、0 より大きい。ゼロ/負数は無効。 |
| `unit_price` | 小数 | 必須、非負。ゼロ価格は警告付きで受理、負価格は無効。 |
| `customer_id` | 文字列 | 任意。空欄可。Unicode で最大 `CUSTOMER_ID_MAX_LENGTH` 文字（既定 128）。ハッシュ ID、UUID、非個人内部キーを使用。メール、電話、氏名など直接識別子は禁止。 |

ファイル単位のルール：

- UTF-8、カンマ区切り、ヘッダー一行。エラー報告ではヘッダーが行 1、最初のデータが行 2。
- 列名は空白除去後に照合し、順序不問。必須 6 列または `customer_id` 以外は警告（`extra_column`）付きで無視し保存しない。
- `(order_id, product_id)` は一意。同一商品は一注文に一度まで。
- ファイル全体で一つの `product_id` に一つの名前。
- 注文内の空 `customer_id` は唯一の非空 ID で補完。競合 ID はアップロード拒否、全空欄注文は未識別。
- アップロードごとに一通貨。フォームで選択（[通貨](#通貨)参照）。
- 無効行が一つでもあればファイル全体を拒否し、何も保存しない。
- 既定で最大 50 MB、500,000 行（`MAX_UPLOAD_BYTES` と `MAX_ROWS`）。
- 数量は最大 2,147,483,647 の整数。価格は通貨記号や桁区切りなしの小数で、小数点前最大 14 桁、後最大 4 桁。

### 有効な例

`example.csv` として保存します。3 明細 2 注文で、注文 `A-1001` は 2 明細です。

```csv
order_id,order_date,product_id,product_name,quantity,unit_price
A-1001,2025-03-01,P-10,Ceramic Mug,2,12.50
A-1001,2025-03-01,P-20,Travel Tumbler,1,24.00
A-1002,2025-03-02,P-10,Ceramic Mug,1,12.50
```

任意の `customer_id` を含められ、空セルも許可されます。

```csv
order_id,order_date,product_id,product_name,quantity,unit_price,customer_id
A-1001,2025-03-01,P-10,Ceramic Mug,2,12.50,CUST-007
A-1001,2025-03-01,P-20,Travel Tumbler,1,24.00,
```

アプリがポート 8000 で動作中なら API からインポートします。

```sh
curl -F currency=USD -F file=@example.csv http://localhost:8000/api/datasets
```

レスポンスは `201` で、`"warnings":[]`、`dataset_id`、`token`、最初のサマリーを含みます。総売上は 2 注文、4 個から 61.50 です。

### 無効な例

各項目は有効ファイルへの小さな変更です。アプリは `422`、エラーコード `validation_failed`、エラー一覧を返し、各エラーの `code` は下表どおりです。行番号と列も含みます。

| 有効ファイルへの変更 | エラー `code` | 行 |
| --- | --- | --- |
| ヘッダーから `unit_price`（および各行の末尾値）を削除 | `missing_column` | なし（ファイル単位） |
| 日付 `2025-03-02` を `2025-13-02` に変更 | `invalid_date` | 4 |
| 最終行の数量を `1` から `0` に変更 | `invalid_quantity` | 4 |
| 最終行を複製 | `duplicate_line` | 5 |

### エラーコード

報告は先頭 100 エラーと合計（`error_count`）を示します。

| コード | 原因 |
| --- | --- |
| `file_too_large` | ファイルが `MAX_UPLOAD_BYTES` より大きい。 |
| `empty_file` | ファイルが空。 |
| `invalid_encoding` | 有効な UTF-8 でない。 |
| `malformed_csv` | CSV として読めない（例：一フィールドが 131,072 文字超）。 |
| `too_many_rows` | データ行が `MAX_ROWS` 超。 |
| `no_data_rows` | ヘッダーはあるがデータ行なし。 |
| `missing_column` | 必須 6 列の一つがヘッダーにない。 |
| `duplicate_column` | 必須列がヘッダーに複数回出現。 |
| `missing_value` | 必須値が空。 |
| `invalid_date` | `order_date` が `YYYY-MM-DD` の実在日でない。 |
| `future_date` | `order_date` が今日（UTC）より後。 |
| `invalid_quantity` | `quantity` が 1～2,147,483,647 の整数でない。 |
| `invalid_price` | `unit_price` が小数点前 14 桁・後 4 桁以内の通常小数でない。 |
| `negative_price` | `unit_price` がゼロ未満。 |
| `line_total_too_large` | `quantity × unit_price` が 100,000,000,000,000 以上で、総売上の厳密小数範囲外。 |
| `malformed_row` | 行の値数がヘッダーと異なる。 |
| `duplicate_line` | 同じ `order_id` と `product_id` が前行に存在。 |
| `conflicting_product_name` | 一つの `product_id` に複数の `product_name`。 |
| `conflicting_customer_id` | 一注文に複数の非空 `customer_id`。 |
| `customer_id_too_long` | 非空 `customer_id` が Unicode で `CUSTOMER_ID_MAX_LENGTH` 文字超。 |
| `customer_id_looks_like_email` | 非空 `customer_id` が明白なメールヒューリスティックに一致。 |
| `customer_id_looks_like_phone` | 非空 `customer_id` が明白な電話ヒューリスティックに一致。 |

3 つの `customer_id` 検査はベストエフォートのガードレールで、匿名化でも適合保証でもありません。メール検査は値中の `[^@\s]+@[^@\s]+\.[A-Za-z]{2,}` を探します。電話検査は数字、空白、`+ - . ( )` のみ、数字 7～15 桁、先頭 `+`、見える空白/括弧、または 2 個以上の `-`/`.` 区切りを要求します。既知の見逃しがあります。`05321234567` のような全数字電話は受理され、`2024-01-000123` のようなハイフン 2 個の数字群は拒否されます。受理 ID が匿名になるわけではありません。

ファイル読取前に失敗する場合もあります。リスト外通貨は `400 invalid_request` です。

### 顧客カバレッジ

`customer_id` がある場合、同一注文の別明細から空 ID を補完した後、インポート時に注文単位で一度計算します。

`identified distinct orders / all distinct orders`

行の割合ではないため、5 明細の識別済み注文も一度だけ数えます。データセットメタデータは件数と丸めた比率を報告し、階層は全データセットの正確な整数件数で決まります。

- 50% 未満：`suppressed`。顧客分析は利用不可。
- 50% 以上 80% 未満：`warning`。顧客分析は低カバレッジ警告付きで利用可。
- 80% 以上：`normal`。通常どおり利用可。

`customer_id` なしのファイルは 0% でなく階層 `missing`、`coverage: null` です。カバレッジメタデータは件数だけで顧客 ID を含みません。日付範囲カバレッジも両端を含む注文日で同じ式を使い、空範囲は件数ゼロ、`coverage: null` です。階層は全データセット基準なので、日付絞り込みで顧客モジュールが出入りしません。

### 顧客 API

`GET /api/datasets/{id}/customers` は bearer トークン保護され、概要・商品モジュールと同じ任意の `start`、`end`、`comparison` クエリを受け付けます。パラメーターなしでは全データセットと既定 `previous_period` 比較です。無効、逆順、範囲外の日付は `400 invalid_range`、未知比較は `400 invalid_request`。資格情報欠落/不正は `WWW-Authenticate: Bearer` 付き `401 unauthorized`、未知・失効・削除済みデータセットは `404 not_found`。

型付きレスポンスは `module`、`range`、`comparison`、`currency`、`availability`、`coverage`、`sections` を含みます。`coverage.dataset` は保存済み全体カバレッジ、`coverage.range` は選択した両端含有範囲カバレッジで、両方に階層、丸め比率、識別済み/未識別/全注文数があります。正常/警告時、`sections.identified_customers` は範囲内で活動した個別識別済み顧客と共通比較値・変化フィールドを報告します。空の活動母集団は `zero_result`。`sections.new_vs_returning` は範囲内識別総売上を新規顧客販売（初回購入日の明細）とリピーター販売（後日明細）に分け、同じ比較フィールドを持ちます。分類は常に全アップロード履歴の `first_order_date` を使うため、範囲開始を動かしてもリピーターは新規になりません。

`sections.days_between_purchases` は現在範囲の再注文タイミングだけを報告し、比較フィールドはありません。各識別済み顧客の個別注文を最初の明細日で並べ、連続ペアを暦日間隔とし、同日 2 注文は `0`。後の注文が両端含有範囲内なら前が範囲開始前でも含み、範囲終了後は無視します。`median_days`（偶数個なら中央 2 値の平均なので `.5` になり得る。平均値そのものは報告しない）、`interval_count`、`contributing_customers`、固定 9 `buckets`（`0`、`1-7`、`8-14`、`15-30`、`31-60`、`61-90`、`91-180`、`181-365`、`366+` 日）を返し、各バケットに `interval_count` と全間隔の `share` があります。間隔なしでは中央値と全シェアが `null`、状態は `insufficient_data`。

`sections.cohort_retention` は現在範囲だけの月次獲得コホート継続率行列（比較なし）です。顧客コホートは全履歴初回注文月です。行は範囲開始月から終了月まで古い順で、開始だけ動かしても行は変わりません。範囲終了日が `data_cutoff` で、それ以後に初出の顧客は非メンバー、後続活動は無視、開始前活動は計数します。各行は `cohort_month`（`YYYY-MM`）、`cohort_size`、`complete_months`、`cells` を持ち、月 `N`（0 = 獲得月）は `retained_count`（その暦月に識別明細があるメンバー）と `retention`（`retained_count / cohort_size`）を持ちます。セルの `state` は `complete`（月全体がカットオフ以前）、`partial`（カットオフを含み途中まで）、`not_observed`（月開始がカットオフ後、値は `null` で `0` ではない）。最古コホートと同じ幅まで行を埋めます。重なるコホートなしでは `rows` が空、状態 `insufficient_data`。

`sections.historical_customer_value` は現在範囲だけの観測済み過去顧客価値（既に観測した総売上、予測ではない）です。母集団は `cohort_retention` 行メンバーで、顧客価値は `data_cutoff`（範囲終了）以前の識別総売上（開始前も含む）。`customer_count`、`average`（総価値 / `customer_count`）、`median`（偶数なら中央 2 値平均）を返し、金額は half-up で小数 4 桁。`rows` は `cohort_retention` の行と状態に対応し、セル `value_per_customer` = コホートの月 `N` 末までの累積総売上（カットオフ上限）/ `cohort_size`（`not_observed` は `null`）。`all_cohorts` はセルが `complete` のコホートについて月オフセットごとに一点（`value_per_customer`、`contributing_cohorts`。完全セルなしは `null` と `0`）。コホートなしは `insufficient_data`、メンバー総価値 0 は `0.0000` 値の `zero_result`。

`sections.rfm` は現在範囲の RFM セグメント件数だけを報告し、比較なし。母集団（`customer_count`、N）は範囲終了以前に識別注文がある顧客で、それまでの全識別活動を数え、開始は影響しません。Recency は最新識別明細から `recency_anchor`（範囲終了）までの日数、frequency は個別注文、monetary は総売上です。各次元を順位から 1-5 点：`floor(5 × (2 × worse + ties) / (2 × N)) + 1`。`worse` は厳密に悪い値、`ties` は同値顧客数なので、同値は同点、定数次元は 3 点。`FM = F + M` とし、最初の一致規則で Champions (R ≥ 4, FM ≥ 8)、Loyal (R ≥ 3, FM ≥ 6)、Potential Loyalists (R ≥ 4, FM ≤ 5)、Needs Attention (R = 3, FM ≤ 5)、At Risk (R ≤ 2, FM ≥ 6)、Lost (R ≤ 2, FM ≤ 5)。`segments` は常にこの順で 6 種すべてと `customer_count`、`share` を列挙し、顧客別スコアはバックエンド外へ出ません。5 顧客未満では空 `segments` と `insufficient_data`。固定 `note` は、本アップロード顧客基盤相対で普遍的ベンチマークでないと伝えます。

`sections.rfm_drilldown` は `sections.rfm` と同じ母集団、入力、セグメントで RFM 別集計を報告し、比較なし。最上位は `customer_count`（N、`sections.rfm` と同じ）、`recency_anchor`（範囲終了）、`gross_sales`（終了までの N 顧客金額合計、half-up 小数 4 桁）を返します。`segments` は `sections.rfm` 順に 6 種すべてを列挙し、それぞれ `customer_count`、`gross_sales`（メンバー金額合計）、`gross_sales_share`（セグメント `gross_sales` / 最上位 `gross_sales`、合計 `0` は `null`）、アンカーまでの日数を 6 固定バケットにした `recency_distribution`（`0-30`、`31-60`、`61-90`、`91-180`、`181-365`、`366+`。`key`、`min_days`、`max_days`、`customer_count`）、個別注文を 8 固定バケットにした `frequency_distribution`（`1`、`2`、`3`、`4`、`5`、`6-10`、`11-20`、`21+`。`key`、`min_orders`、`max_orders`、`customer_count`）を持ちます。開放バケットの最大値は `null`、空セグメント/バケットは `0`。顧客 ID やスコアを返さないため、一人セグメントも同様に報告。5 顧客未満は実 `customer_count`、`gross_sales`、空 `segments` で `insufficient_data`。

カバレッジ欠落/抑制では全セクションを省略（`sections` は空）。エンドポイントは常に `Cache-Control: no-store`。顧客レスポンスは設計上集計のみで、顧客識別子、顧客レベルオブジェクト、検索、詳細、ダウンロード、エクスポートを返さず、識別子をログへ書きません。

### 警告

警告はファイルを拒否しません。`201` レスポンスの `warnings` 一覧とアップロード画面へ返ります。

| コード | 意味 |
| --- | --- |
| `extra_column` | 必須 6 列または `customer_id` 以外（例：`note`）がある。無視し保存しない。 |
| `zero_price` | 単価 0 の明細がある。総売上なしで注文と個数には数えてインポート。 |

### サンプルデータ

有効なサンプルは <http://localhost:8000/api/sample.csv> からダウンロードできます（画面では **Download sample CSV**）。**Try sample data** はアップロードせず同じファイルを USD でインポートします。

## トレンドバケット

トレンドは総売上を暦バケットで集計します。粒度は両端を含む選択範囲だけで決まり、90 日以下は日次、90 日超 730 日以下は週次、それより長ければ月次です。API はバケット初日の `bucket_start` を返し、カバレッジフィールドはありません。

- 範囲は両端を含み、開始日と終了日の両方が入ります。
- 週は月曜～日曜で、週バケットの `bucket_start` は月曜。月は暦月です。
- 範囲で切られたバケット（最初の週/月が開始日前に始まる、最後が終了日後に終わる）は部分期間です。チャートは範囲と暦から計算し、売上なしの日もカバー済みと数えます。一日の日次バケットは常に完全（データは日付のみ）、週/月の一日切片は部分。範囲が一週/月内ならそのバケットは部分です。
- 部分表示：部分週/月の軸ラベルは `12月29日の週` や月名でなく対象日（`12月29～31日`、`2025年3月10～31日`）。点は白抜き、下に注記、ツールチップに年と `部分期間：<対象日>`。完全バケットにはありません。
- 範囲内行だけを合計するため、部分バケットは対象日の売上だけを含みます。

## 通貨

アップロードフォームで USD、EUR、GBP、TRY、CAD、AUD、JPY、CHF、SEK、PLN を選びます。金額のラベルにすぎず、換算や為替レートはありません。その他のコードは `400 invalid_request` で拒否します。

## プライバシー

- 成否を問わずインポート完了直後に生 CSV を削除。
- 必須列と任意 `customer_id` は `DATASET_DIR` 配下のデータセット別 DuckDB に非公開権限（ファイル `0600`、ディレクトリ `0700`）で保存。
- 顧客 ID は仮名化で匿名ではなく、データセットの 24 時間寿命中保持。ハッシュ ID、UUID、非個人内部キーを使い、メール、電話、氏名など直接 ID はアップロード禁止。
- 顧客 ID 長、メール、電話検査はベストエフォートのガードレールで、匿名化/適合保証ではなく、全種類の個人データを検出できない。
- データセットは `DATASET_TTL_HOURS`（既定 24）後、起動時と以降 `CLEANUP_INTERVAL_MINUTES` ごとの清掃で、または**別のファイルを分析**ですぐ削除。
- 成功モジュールレスポンスは上限付きプロセスローカルキャッシュに `RESPONSE_CACHE_TTL_SECONDS`（既定 300 秒）保持され得る。全リクエストで認可し、データセットとオプション別キー、失効/削除でキャッシュ削除。インスタンス間共有なし。
- アクセスにはランダム bearer トークンが必要。ブラウザは `sessionStorage` に保持しタブ終了で消去。サーバーは SHA-256 ハッシュのみ保持。
- 欠落/失効 ID は 404、既存 ID に誤トークンは 401 なので、ステータスは ID 存在を示す。受容済みリスクで、ID は推測不能な 128 ビットランダム値、トークンなしでは読めない。
- ログはリクエストごとの JSON 一行で、メソッド、パス、状態、時間、データセット ID を含む。追跡用に ID を意図的に記録するが秘密ではなく、トークンなしで使えない。トークン、ファイル内容/名、商品名、注文 ID は記録しない。エラーログは例外クラスとスタックフレームだけでメッセージなし。
- 他サービスへ何も送信しない。
- 顧客 ID 提供時、データセット DuckDB は `customer_facts` も含む。識別済み顧客一人一行で全履歴の初回/最終注文日、獲得月、ライフタイム個別注文、個数、総売上を持つ。未識別注文の行なし。データセットと共に失効し、独立共有 DB ではない。

## デモモード

ホスト型デモは `PUBLIC_DEMO_MODE=true` の公開インスタンスで、組み込みサンプルだけを探索できアップロード不可です。データセットは他と同様に失効（`DATASET_TTL_SECONDS`）し、単一インスタンスです。自身のファイル分析には[自分で実行](#docker-で実行)してください。

`PUBLIC_DEMO_MODE=true` は他人のファイルを受け付けるべきでない公開サーバー向けです。

- `POST /api/datasets` は本文を読まず 403 `upload_disabled`。
- **Try sample data** とサンプルダウンロードは動作。
- アップロード画面は形式と **Try sample data** だけで、ファイル/通貨欄なし。サンプルのみ受付と示し、アップロード用に[Docker で実行](#docker-で実行)へリンク。
- `GET /api/config` は `{"public_demo_mode":true,...}` を返し、画面はこれで判断。
- `MAX_DATASETS` が公開サーバーのディスクを保護。**Try sample data** ごとにデータセットを作り、上限で 503 `capacity_reached`。

## 制限

- 単一インスタンスのみ。水平スケールなし。データセットはそのインスタンスのディスクファイル。
- 再起動を越える保持はベストエフォートで、`DATASET_DIR` がボリューム上の場合のみ。
- アカウント/共有なし。データセットは一ブラウザタブにあるトークンでのみ到達。
- 一ファイル一通貨。
- 顧客別一覧、エクスポート、検索なし。顧客数値は識別済み注文のみ。
- 総売上のみ。返金、値引き、税、送料なし。
- 既定 50 MB、500,000 行。
- 360 px 以上の電話、タブレット、デスクトップ幅。広い表は自身の領域内でスクロール（[`_docs/design-system.md`](_docs/design-system.md)参照）。

## ロードマップ

フェーズ 3 は完了しました。[フェーズ 3 仕様](_docs/open_sales_analytics_phase_3_spec.md#20-deferred-roadmap)の次候補：

- **フェーズ 4：管理製品基盤。** 中央アプリ DB、アカウント、所有権、保存済みデータセット、永続ダッシュボード。
- **フェーズ 4：ホスト型取り込み。** レート制限、分離、悪用対策、監視付きの保護された公開アップロード。
- **フェーズ 4：財務契約レイヤー。** 任意 `discount_amount`、`refund_amount`、`unit_cost` 列と、純売上、値引き、返金、マージン分析。
- **将来：** Shopify、WooCommerce、マーケットプレイス形式マッパー。複数ファイル/チャネル。明確なプライバシーモデルによる顧客活用/エクスポート。大規模非同期インポート。需要検証後だけ予測/異常検知。

## アーキテクチャ

React（Vite）フロントエンドが JSON で FastAPI バックエンドと通信します。各データセットは `DATASET_DIR` 下の DuckDB 一ファイルで、検証と分析はそのファイルへの SQL です。標準インポートは同じファイルに再利用可能な `order_facts`、`product_facts`、識別顧客があれば全履歴 `customer_facts` を構築します。プロセス内バックグラウンドタスクが期限切れを削除します。Docker は単一コンテナで、FastAPI が同一オリジンのポート 8000 から API とビルド済みフロントエンドを配信します。[フェーズ 3 アーキテクチャガイド](_docs/architecture.ja-JP.md)、[指標カタログ](_docs/metrics.ja-JP.md)、[リリースチェックリスト/証拠報告](_docs/phase-3-release-checklist.md)、[フェーズ 3 仕様](_docs/open_sales_analytics_phase_3_spec.md)、[バックログ](_docs/tasks.md)を参照。

## 開発

作業プロセス：[`_docs/process.md`](_docs/process.md)。テスト規約：[`_docs/testing-guidelines.md`](_docs/testing-guidelines.md)。性能基準コマンド/結果：[`_docs/benchmarks.md`](_docs/benchmarks.md)。

リポジトリルートから：

```sh
uv sync
uv run pytest
```

Lint/型チェック（CI と同じ。`uv sync` は `ruff` と `mypy` を開発依存として導入）：

```sh
uv run ruff check backend
uv run ruff format --check backend   # `uv run ruff format backend` fixes it
uv run mypy backend/app
```

依存関係スキャン（CI `dependency-scan` と同じ。`uvx` は `pip-audit` をプロジェクト依存にせず実行）：

```sh
uv export --locked --no-emit-project --format requirements-txt -o /tmp/requirements.txt
uvx pip-audit@2.10.1 -r /tmp/requirements.txt --no-deps --disable-pip
(cd frontend && npm audit --audit-level=high)
```

バックエンド起動（http://127.0.0.1:8000）：

```sh
uv run uvicorn app.main:app --app-dir backend
```

確認：`curl http://127.0.0.1:8000/api/health` は `{"status":"ok"}`。Docker なしでビルド済みフロントエンドを同一オリジン配信するには、先に `frontend/` で `npm run build`（後述）し、上記バックエンドを起動して <http://127.0.0.1:8000> を開きます。

### フロントエンド

Node 22 以降が必要です。`frontend/` から：

```sh
npm ci            # install
npm run dev       # dev server on http://localhost:5173
npm test          # Vitest, single run
npm run lint      # ESLint
npm run typecheck # tsc --noEmit (TypeScript 7)
npm run build     # type check, then the production bundle in frontend/dist
```

`npm run dev` は `/api` をポート 8000 のバックエンドへプロキシするため、バックエンドも起動します。

### 必須 CI チェック

`main` へのマージでは、GitHub がプルリクエストに表示する次の 4 チェックを正確な綴りで要求します（Settings、Branches または Rules、"Require status checks to pass" で各名前を選択）。

- `Backend (tests, ruff, mypy)`
- `Frontend (tests, lint, type check, build)`
- `Dependency scan (Python, npm) / Dependency scan (Python, npm)`
- `Container (build, smoke, browser tests)`

依存スキャンは再利用ワークフロー `.github/workflows/dependency-scan.yml` を呼び、CI 定義は `.github/workflows/ci.yml` にあるため、GitHub は `<calling job> / <called job>` と名前を二重表示します。ブランチ保護では完全な二重名を選び、単独 `Dependency scan (Python, npm)` はチェック実行に一致しません。`.github/workflows/` のジョブ名変更時は同じ変更でこの一覧と保護設定も更新してください。存在しない必須チェックは全マージを阻止します。任意 PR で `gh pr checks <number>` と比較できます。

### 依存関係スキャン

CI は全 PR と `main` への push、および毎週月曜 05:17 UTC（`.github/workflows/dependency-scan-scheduled.yml`）に両ロックファイルをスキャンするため、未変更ロックへの新勧告も次 PR 前に赤になります。両方とも `.github/workflows/dependency-scan.yml` の共通定義を呼び、コマンドと方針は同じです。予定実行は `contents: read`、秘密なしで、Actions の“Run workflow”から手動実行もできます。

| エコシステム | ツールと入力 | CI 失敗条件 |
| --- | --- | --- |
| Python | `uv.lock`（実行/開発パッケージ）への `pip-audit` | 既知脆弱性すべて（pip-audit は重大度フィルターなし） |
| npm | `frontend/package-lock.json` への `npm audit --audit-level=high` | high/critical。low/moderate はログ表示のみ |

スキャナーエラー（ネットなし、不正入力）も失敗します。`|| true` や `continue-on-error` はなく、無視一覧もありません。修正なし勧告には、スキャンコマンド横に ID と理由を書き、`pip-audit --ignore-vuln ID` で例外固定またはパッケージ削除するレビュー済み PR が必要で、黙ってスキップしません。キャッシュはパッケージダウンロードと Playwright ブラウザだけで、データセット、アップロード、秘密、DuckDB を制作品としてキャッシュ/送信しません。

Dependabot（`.github/dependabot.yml`）は毎週月曜、既存 Python（`pyproject.toml` 由来 `uv.lock`）と npm（`frontend/package-lock.json`）依存を更新し、各エコシステム最大 5 PR。既存依存だけを上げ、新規追加しません。同じ CI を秘密なし（読み取り専用トークン）で行い、更新ロック上でスキャン、テスト、ビルド、ブラウザを実行します。他と同様にリリースノートとロック差分を読み、全チェック緑だけをマージし、メジャー更新は手動実行もします。赤チェックは閉じる/修正する理由で、マージしません。

予定実行失敗は Actions に赤い“Dependency scan (scheduled)”として表示（名前または `event:schedule` で絞り込み）。GitHub は所有者にもメールし、予定ワークフローは最後に `cron` 行を変えたユーザーへ通知するため、他者が変更したら Settings、Notifications、Actions が有効か確認します。既定ブランチだけで動き、リポジトリ活動が 60 日ないと GitHub が一時停止するため、Actions から再有効化します。

### コンテナイメージの固定

決定：`Dockerfile` の基本イメージ（`node:22`、`python:3.12-slim`）はダイジェスト（`FROM image:tag@sha256:...`、マルチアーキテクチャ索引）で固定。タグは移動し同一コミットのビルドが異なり、未レビュー上流変更が破損/侵害し得るため、ダイジェストで再現可能にし、基本イメージ変更を PR レビュー対象にします。Dependabot（`.github/dependabot.yml` の `docker`、月曜）がタグとダイジェストを同時更新し、`docker-smoke` CI がマージ前に構築/起動。手動更新は必要タグのダイジェストを調べ `FROM` の両方を置換。`COPY --from=ghcr.io/astral-sh/uv:0.8` の `uv` は現時点でタグのままです。

### Actions の固定

`.github` 配下の `uses:` がローカルパス（`./.github/workflows/...`）でも `owner/repo@<40 hex characters>` でもなければ `pinned-actions` が失敗し、注釈にファイル/行を示します。`uses: owner/repo@<sha> # vX.Y.Z` と書き、Dependabot が SHA とコメントを更新します。このチェックは `contents: read` の shell で、`actions/checkout` 以外の秘密/第三者 Action がなく、fork/Dependabot PR でも動きます。

### ブラウザテスト

小規模 Playwright（Chromium、`frontend/e2e/`）が主要ジャーニーをカバーします。Try sample data、有効/無効アップロード、日付範囲/Reset、Analyze another file、横断顧客ジャーニー、360/768/1280 px 応答レイアウト、期限切れデータセットです。
ブラウザを一度インストール（約 150 MB、リポジトリ外）して `frontend/` から実行します。

```sh
npx playwright install chromium
npx playwright install-deps chromium   # Linux only: system libraries, needs sudo; CI runs it too
npm run e2e
```

`npm run e2e` はバックエンド（8000）と Vite（5173）を一時データセットディレクトリで起動し後で停止します。両ポートを空けてください。既に動くアプリ（例：コンテナ）には `E2E_BASE_URL` を設定し、サーバーを起動しません。そのアプリは `DATASET_TTL_SECONDS=60` で実行する必要があり、失効ジャーニーが有界ポーリングで実失効を待ちます。

```sh
docker build -t open-sales-analytics .   # from the repository root
docker run -d --name oca -p 8000:8000 -e DATASET_TTL_SECONDS=60 open-sales-analytics
curl -f http://localhost:8000/api/health   # answers {"status":"ok"}; repeat for a few seconds until it does
curl -f http://localhost:8000/d/anything | grep -i '<div id="root"'   # the single-page app
E2E_BASE_URL=http://localhost:8000 npm run e2e
docker rm -f oca
```

失敗時はトレースとスクリーンショットを `frontend/test-results/` に保存（`npx playwright show-trace` で開く）。`CI` 設定時（GitHub Actions）はネットワークレスポンスを含むためトレースを記録せず、失敗スクリーンショットだけをアップロードします。

## コントリビューション

バグ報告、アイデア、プルリクエストを歓迎します。[`CONTRIBUTING.md`](CONTRIBUTING.ja-JP.md)を参照してください。

## ライセンス

[Apache License, Version 2.0](LICENSE) の下でライセンスされています。
