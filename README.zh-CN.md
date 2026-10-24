# open-sales-analytics

语言：[English](README.md) | [Türkçe](README.tr-TR.md) | [Deutsch](README.de-DE.md) | [Русский](README.ru-RU.md) | [Español](README.es-ES.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja-JP.md)

> 本译文以[英文原文](README.md)为准；同步修订版本 `045796b0c7bbdd21520ccce1c7972495aab929f8`，同步日期 `2026-10-22`。

Open Sales Analytics 是一款小型自托管 Web 应用。上传已完成销售明细的 CSV 后，它会显示总销售额、订单数、件数、平均订单价值、销售趋势和畅销产品，并可更改日期范围。总销售额是所选期间内各行的数量乘以单价之和，不包含退款、折扣、税费或运费。

目录：[使用 Docker 运行](#使用-docker-运行) | [配置](#配置) | [演示导览](#演示导览) | [查看结果](#6-查看结果) | [产品分析](#产品分析) | [客户分析](#客户分析) | [比较](#比较) | [数据集契约](#数据集契约) | [货币](#货币) | [隐私](#隐私) | [演示模式](#演示模式) | [限制](#限制) | [路线图](#路线图) | [架构](#架构) | [开发](#开发) | [贡献](#贡献) | [许可证](#许可证)

## 使用 Docker 运行

目前没有发布的镜像，因此需要先从本存储库的检出版本构建一次，再运行：

```sh
docker build -t open-sales-analytics .
docker run -p 8000:8000 open-sales-analytics
```

打开 <http://localhost:8000>。您会看到上传页面；**试用示例数据**会用样例文件打开仪表板。`curl http://localhost:8000/api/health` 返回 `{"status":"ok"}`。

容器以非 root 用户（UID 10001）运行，并将数据集保存在 `/data`（`DATASET_DIR=/data`）。未挂载卷时，删除容器也会丢失数据。要保留数据，请将命名卷挂载到 `/data`：

```sh
docker run -p 8000:8000 -v osa-data:/data open-sales-analytics
```

使用卷后，数据集会尽力在 `docker restart` 和重建容器后保留，但仍会在 `DATASET_TTL_HOURS` 后过期。若在 `/data` 挂载主机目录而非命名卷，该目录必须允许容器的非 root 用户（UID 10001）写入，例如 `sudo chown 10001 /path/to/dir`。

镜像具有自检：启动数秒后 `docker ps` 显示 `healthy`；`/api/health` 停止响应时显示 `unhealthy`（每 10 秒检查，超时 3 秒，失败 3 次，启动宽限 10 秒）。`docker stop` 会先停止后台清理，再于一秒内以退出码 0 结束服务器。服务器本身不设请求超时（采用 uvicorn 默认值），因此很慢的上传只会在客户端放弃时终止。

用 `-e` 传入[下表](#配置)中的设置：

```sh
docker run -p 8000:8000 -e PUBLIC_DEMO_MODE=true -e OSA_ENVIRONMENT=production -e OSA_VERSION=20261024-123456-abc1234 open-sales-analytics
```

## 演示导览

以下步骤使用生成的样例数据，从全新检出一直运行到仪表板。第 1 步需要 [uv](https://docs.astral.sh/uv/)；其余步骤只需 Docker。

### 1. 生成样例数据

```bash
uv run python backend/scripts/generate_sample.py
```

这会写入 `backend/app/sample/sample_sales.csv`。种子使文件具有确定性，因此每个人都会得到相同数据以及第 6 步的相同数值。请在 `docker build` 前运行，因为该文件会复制进镜像。

检查前几行：

```bash
head -n 4 backend/app/sample/sample_sales.csv
```

```
order_id,order_date,product_id,product_name,quantity,unit_price,customer_id
ORD-000001,2024-01-01,P001,Ceramic Mug,1,12.00,CUST-6ebe7ed43ba4
ORD-000001,2024-01-01,P002,Travel Tumbler,1,24.00,CUST-6ebe7ed43ba4
ORD-000002,2024-01-01,P001,Ceramic Mug,1,12.00,CUST-c4da5c3ce3f2
```

### 2. 构建镜像

```bash
docker build -t open-sales-analytics .
```

### 3. 运行容器

```bash
docker run -p 8000:8000 open-sales-analytics
```

日志显示 `Uvicorn running on http://0.0.0.0:8000` 时服务器已就绪。

### 4. 打开 Web 界面

打开 <http://localhost:8000>。上传页面会显示文件格式和上传表单。

### 5. 上传样例数据

选择 `backend/app/sample/sample_sales.csv`，选择 **USD** 并单击**上传**。（**试用示例数据**无需选择文件即可导入同一文件。）

![已选择样例文件和 USD 的上传表单](_docs/images/demo-upload.png)

### 6. 查看结果

仪表板会在**概览**中打开，显示数据的完整周期 2024-01-01 至 2025-12-31：

| 指标 | 预期值 |
| --- | --- |
| 行数 | 14,397 |
| 总销售额 | $675,816.70 |
| 订单 | 10,000 |
| 售出件数 | 24,380 |
| 平均订单价值 | $67.58 |

![概览：关键数值、月度总销售额趋势和前 10 个产品](_docs/images/phase-3/overview.png)

完整周期为 24 个月，因此趋势按月显示（参见[趋势分桶](#趋势分桶)）。更改**开始日期**和**结束日期**会筛选所有数值；**重置**恢复完整周期。**比较对象**可加入上一周期或去年同期；由于数据从 2024-01-01 开始，完整周期无法比较。

**商品**页面显示排名、总销售额份额及累计 Pareto 图、上升和下降产品、休眠产品和搭配购买产品；此处比较 2025 与 2024（参见[产品分析](#产品分析)）：

![产品：排名、Pareto 图、上升和下降产品、休眠和产品组合](_docs/images/phase-3/products.png)

点击产品名称打开详情：总销售额趋势、每件平均实付价格、订单渗透率和相关产品。

![产品详情：总销售额趋势、加权单价、订单渗透率和相关产品](_docs/images/phase-3/product-detail.png)

**客户**页面显示覆盖率、客户关键指标、购买间隔天数、同期群留存热图、历史客户价值、预计 12 个月客户价值、RFM 分群、购买频率和集中度（参见[客户分析](#客户分析)）：

![客户：覆盖率、关键指标、同期群留存热图、价值、RFM、频率和集中度](_docs/images/phase-3/customers.png)

**分析另一个文件**会删除当前数据集并返回上传页面。

## 比较

日期范围卡可将活动范围与上一周期或去年同期比较。仪表板显示 API 返回的确切日期。若比较期早于数据集首日，完整范围比较不可用。涉及闰日时，使用比较年份二月的最后一个有效日期。没有先前值时标为“无先前值”；两个零值标为“无变化”；新产品标为“新产品”；其他情况的百分比标为“可比较”。

## 产品分析

除非另有说明，所有产品数值均使用选定且包含首尾日期的活动范围。金额均为总销售额；折扣、退款和成本不在数据集契约内。每个产品名称和 ID 都按服务器提供的文本显示。

| UI 标签和键 | 公式和分母 | 窗口及非正常状态 | 示例 |
| --- | --- | --- | --- |
| 排名 — `gross_sales` | 数量 × 单价之和；售出件数为数量之和；订单为不同订单数 | 活动范围；空范围没有产品 | 2 件、单价 12.50 的行贡献 25.00 总销售额 |
| 总销售额份额 — `gross_sales_share` | 产品总销售额 / 所有产品总销售额 | 活动范围；总销售额为零时数据不足 | 100 中的 15 为 15.00% |
| 前 20% 份额 — `top_20_percent_share` | 排名前 20% 产品数量的总销售额 / 总销售额 | 活动范围；总额为零时数据不足 | 五个产品为 50/20/15/10/5：第一名为 50.00% |
| 达到 80% 所需产品数 — `products_to_80_percent` | 累计份额达到 80% 的最小有序产品数 | 活动范围；总额为零时数据不足 | 50+20+15 在第 3 个产品达到 80% |
| 累计份额 — `cumulative_share` | 累计总销售额 / 总销售额 | 活动范围；总额为零时不可用 | 前三个黄金产品达到 85.00% |
| 产品增长 — `product_growth` | 当前总销售额减比较期总销售额；百分比以比较值为基数 | 比较期；`新产品`、`当前无销售`、`无变化` 或比较不可用时不显示误导性百分比 | 10 到 20 为 +10 和 +100.00% |
| 上升/下降排名 — `rising_products`, `falling_products` | 按总销售额绝对变化排名 | 选定比较；比较不可用时不可用 | +10 的变化排在变化 +1（+900%）之前 |
| 休眠产品 — `dormancy` | 在选定 30、60 或 90 天窗口内无销售的产品；较早总计使用窗口之前的销售 | 锚定选定范围结束日（完整范围时为数据集最晚日期），默认 60；历史不足与零结果不同。锚点前恰好 N 天的销售属于窗口 | 最后一次销售恰在锚点前 60 天的产品包含在 60 天窗口内 |
| 加权单价 — `weighted_unit_price` | SUM(quantity × unit price) / SUM(quantity) | 活动范围分桶；无销售分桶为空缺而非零价格 | 1 件 10 加 3 件 20 得 17.50 |
| 订单渗透率 — `order_penetration` | 包含产品的不同订单数 / 所有不同订单数 | 活动范围；零订单是零结果 | 200 个订单中的 25 个为 12.50% |
| 支持度 — `basket_support` | 共同订单 / 合格购物篮订单 | 活动范围；要求至少 10 个共同订单且支持度 0.1% | 10,000 个订单中 10 个共同订单为 0.10% |
| 置信度 — `basket_confidence` | 共同订单 / 包含方向起点产品的订单 | 活动范围；低于阈值的组合不显示 | 因订单数不同，A→B 与 B→A 可能不同 |
| 提升度 — `basket_lift` | 置信度 / 目标产品支持度 | 活动范围；低于阈值的组合不显示 | 将观察到的组合率与目标产品支持度比较 |

共享注册表将这些键标记为：Gross-sales share、Cumulative gross-sales share、Top 20% product share、Products to 80% of gross sales、Product gross-sales growth、Rising products、Falling products、Dormant products、Weighted realized unit price、Order penetration、Basket support、Basket confidence 和 Basket lift。

低于任一购物篮阈值的组合不会显示，即使提升度很高。含超过 100 种不同产品的订单仅从购物篮分析中排除；恰好 100 种会包含，并仍计入排名、渗透率和总销售额。产品页会报告排除数量。价格历史只描述实际价格变化，不衡量价格弹性，也不表示价格变化导致销售变化。上升和下降按绝对变化排序，避免微小基线占据优势。渗透率、支持度、置信度和提升度均使用不同订单。

API 文档位于 [`/docs`](http://localhost:8000/docs)。`GET /api/datasets/{id}/overview` 返回概览 KPI 和趋势；`GET /api/datasets/{id}/products` 返回产品组合分析；`GET /api/datasets/{id}/products/detail?product_id=...` 返回单个产品的详情分析。数据集端点需要该数据集的 bearer 令牌。

## 客户分析

客户分析仅提供聚合信息。它描述已识别订单，绝不显示客户标识符、客户列表或每客户金额。活动报告范围包含开始日和结束日，除非某行明确描述截至选定结束日的完整历史。以下示例使用已提交的 `backend/tests/fixtures/customers/golden_customers.csv` 固定数据：2025-01-01 至 2025-09-30 有 20 个订单、19 个已识别订单、10 名客户和 380.0000 已识别总销售额。

| UI 标签和键 | 公式、窗口和锚点 | 数据不足和零结果 | 示例 |
| --- | --- | --- | --- |
| 客户覆盖率 — `customer_coverage` | 不同已识别订单 / 所有不同订单；按订单统计，适用于数据集和选定范围 | 无 `customer_id` 列即不可用，低于 50% 时抑制，无订单时覆盖率为 null | 黄金固定数据中 19 / 20 = 95.0% |
| 已识别客户 — `identified_customers` | 活动范围内有已识别行的不同 `customer_id` 值；范围首尾均包含 | 无已识别客户时以 `zero_result` 返回 0 | 黄金范围有 10 名 |
| 新客户与回访客户总销售额 — `new_vs_returning` | 按每行是否处于客户完整历史的首次订单日期或之后，拆分 `SUM(quantity × unit_price)`；历史截至范围结束 | 无已识别行时以 `zero_result` 返回零金额 | CUST-01 在 2024-12-15 的购买使其 2025 年销售归为回访 |
| 重复购买率 — `repeat_purchase` | 截至选定结束日至少有两个不同订单的活动客户 / 活动已识别客户；范围开始前订单计入 | 无活动客户为 `insufficient_data`；有活动客户但无重复购买恰为 0（`zero_result`） | 同日订单是不同订单，不是不同日期 |
| 购买间隔天数 — `days_between_purchases` | 连续不同订单间日历日数的中位数；后一个订单在范围内即计入；同日订单为 0 | 无间隔时中位数为 null 且为 `insufficient_data`；固定桶为 0、1-7、8-14、15-30、31-60、61-90、91-180、181-365、366+ | 同日订单对计入桶 0 |
| 同期群留存 — `cohort_retention` | 按日历月偏移计算留存客户 / 完整历史获客同期群规模；同期群使用截至选定结束日的全部历史 | 缺少同期群为 `insufficient_data`；右侧边缘单元格为 `尚未观察`，绝非 0% | 每个非空同期群的第 0 月为 100.0% |
| 历史客户价值 — `historical_customer_value` | 截至结束日观察到的已识别总销售额 / 已识别客户数；中位数为每客户价值中间值；同期群曲线使用累计销售额 | 无同期群为 `insufficient_data`；观察销售额为零是零结果；这是观察数据而非预测 | 黄金固定数据为 10 名已识别客户共 380.0000 |
| RFM 分群 — `rfm` | 最近购买为选定结束日前的天数；频率为不同订单数；金额为已识别总销售额。各维度使用相对五分位分数，FM = F + M | 少于 5 名客户为 `insufficient_data`；并列值分数相同，完整的分数到分群表在注册表中 | 分数相对于本次上传，并非通用基准 |
| RFM 分群下钻 — `rfm_drilldown` | 分群聚合总销售额，以及固定的最近购买桶（0-30 至 366+）和频率桶（1、2、3、4、5、6-10、11-20、21+）；无逐客户行 | 少于 5 名客户为 `insufficient_data`；总销售额为零时份额为 null | 黄金固定数据含无 ID 决胜规则的并列值 |
| 购买频率 — `purchase_frequency` | 按截至选定结束日的不同已识别订单数将客户分为 1、2、3、4、5、6-10、11-20 和 21+ | 无已识别客户时计数为空、份额为 null 且为 `insufficient_data` | 有两个订单的客户属于桶 2 |
| 客户集中度 — `concentration` | 前十分位总销售额 / 已识别总销售额；N 名客户的顶部组取 `ceil(N / 10)` 个最大范围销售值，截止处不按并列值打破顺序 | 少于 10 名客户或已识别总销售额为零时为 `insufficient_data` 且份额为 null | N=10，销售为 1000、500 和八个 100 时，1000 / 2300 = 0.4348 |

50% 和 80% 覆盖等级的边界均包含如下：低于 50% 时隐藏；50.0% 至不足 80% 显示低覆盖警告；80% 或以上为正常。UI 将显示的百分比截断为一位小数，不会通过四舍五入跨越等级边界。覆盖率按订单而非行计算。缺少该列的文件为不可用，而非 0%。

客户身份和同期群使用截至选定结束日的完整历史。向后移动范围开始日不会把客户重新归类为新客户，也不会改变同期群归属。RFM 最近购买与同期群成熟度锚定选定结束日，而不是今天。部分或未来的同期群单元格为**尚未观察**，并非零结果。

上传一致性规则是精确的：一个订单内的空值会由其唯一非空 ID 填充；两个不同 ID 会拒绝整个上传；全空订单仍未识别。`customer_id` 默认限制为 128 个字符。尽力而为的检查会拒绝明显的电子邮件、电话号码和超过限制的值；无法识别姓名、邮政地址、身份证号码、可逆编码或非常规电话格式。

客户数据是假名化而非匿名数据。请使用 UUID、内部键或带文件外保管的秘密盐值的哈希。响应只含聚合计数和总和：无客户列表、搜索、下载或导出，也不记录客户 ID、同期群归属和 RFM 记录。客户数据仅存在于数据集 DuckDB 文件中，会在 `DATASET_TTL_HOURS`（默认 24）后随文件删除，或通过**分析另一个文件**立即删除；原始 CSV 在导入后删除。预计 12 个月客户价值是独立的未来指标，并非此观察指标。

## 配置

服务器启动时读取以下环境变量，全部为可选项。

| 变量 | 类型 | 默认值 | 作用 |
| --- | --- | --- | --- |
| `DATASET_DIR` | 路径 | `./tmp_datasets`（Docker 镜像中为 `/data`） | 每个数据集一个 DuckDB 文件的目录；缺失时以私有权限创建。 |
| `DATASET_TTL_HOURS` | 大于 0 的整数 | `24` | 数据集过期并删除前的小时数。 |
| `DATASET_TTL_SECONDS` | 大于 0 的整数 | 未设置 | 仅测试使用。设置后以秒为生命周期，替代 `DATASET_TTL_HOURS`。浏览器测试借此观察真实过期；生产环境应不设置。 |
| `MAX_UPLOAD_BYTES` | 大于 0 的整数 | `52428800`（50 MB） | 可接受的最大上传字节数；更大文件以 `file_too_large` 拒绝。 |
| `MAX_ROWS` | 大于 0 的整数 | `500000` | 单次上传最多数据行数（不计表头）；更多时以 `too_many_rows` 拒绝。 |
| `CUSTOMER_ID_MAX_LENGTH` | 大于 0 的整数 | `128` | 非空 `customer_id` 的最大 Unicode 字符数；更长时以 `customer_id_too_long` 拒绝。 |
| `CLEANUP_INTERVAL_MINUTES` | 大于 0 的整数 | `15` | 服务器删除过期数据集的频率（启动时也执行一次）。 |
| `PUBLIC_DEMO_MODE` | 布尔值 | `false` | `true` 会关闭上传，参见[演示模式](#演示模式)。 |
| `MAX_DATASETS` | 大于 0 的整数 | `200` | 服务器最多保存的未过期数据集。再创建一个（上传或**试用示例数据**）会返回 503 `capacity_reached`，直到有数据集过期或删除。 |
| `RESPONSE_CACHE_MAX_ENTRIES` | 大于等于 0 的整数 | `256` | 此进程中缓存的概览/产品响应上限。`0` 禁用响应缓存。 |
| `RESPONSE_CACHE_TTL_SECONDS` | 大于 0 的整数 | `300` | 缓存概览/产品响应的最长生命周期；数据集过期始终优先。 |
| `OSA_ENVIRONMENT` | `development` or `production` | `development` | 运行环境。其他值会阻止启动。 |
| `OSA_VERSION` | string | `local` | 易读的版本。CI 设置镜像构建版本；可用 `docker run -e` 覆盖。 |

布尔值不区分大小写，可用 `true`/`false`、`1`/`0` 和 `yes`/`no`（`on`/`off`、`t`/`f`、`y`/`n` 也可）。

无效值会让服务器拒绝启动，并在错误中指出变量。无效包括非数字、零或负数、如 `1.5` 的小数、空字符串，或不属于上述拼写的布尔值。例如 `MAX_ROWS=0 uv run uvicorn app.main:app --app-dir backend` 会以 `MAX_ROWS  Input should be greater than 0` 退出。

## 数据集契约

每行代表一个已完成订单内的一条产品明细。文件必须含以下六个必需列和一个可选列（上传页面也显示同一张表）。`customer_id` 的含义及隐私限制见[客户分析](#客户分析)：

| 列 | 类型 | 规则 |
| --- | --- | --- |
| `order_id` | 字符串 | 必填且非空，用于不同订单计数。 |
| `order_date` | 日期 | 必须是 `YYYY-MM-DD` 格式的 ISO 日历日期，不得为未来日期。 |
| `product_id` | 字符串 | 必填且非空，用于标识产品。 |
| `product_name` | 字符串 | 必填且非空；同次上传中一个 `product_id` 必须恰好对应一个名称。 |
| `quantity` | 整数 | 必填且大于零；零和负数无效。 |
| `unit_price` | 小数 | 必填且非负；零价格会接受并给出警告，负价格无效。 |
| `customer_id` | 字符串 | 可选，可为空；最多 `CUSTOMER_ID_MAX_LENGTH` 个 Unicode 字符（默认 128）；使用哈希标识符、UUID 或非个人内部键，绝不可使用邮箱、电话号码、姓名或其他直接标识符。 |

文件级规则：

- UTF-8、逗号分隔、一个表头行。错误报告中表头为第 1 行，因此第一条数据为第 2 行。
- 列名去除空格后匹配，顺序无关。不属于六个必需列或 `customer_id` 的列会忽略并给出警告（`extra_column`）。
- `(order_id, product_id)` 唯一：同一产品在每个订单中最多出现一次。
- 整个文件中每个 `product_id` 只能有一个名称。
- 每个订单内，空白 `customer_id` 会由其唯一非空 ID 填充；冲突 ID 会拒绝上传，全空订单保持未识别。
- 每次上传一种货币，在上传表单中选择（参见[货币](#货币)）。
- 任意无效行都会拒绝整个文件，不存储任何内容。
- 默认最多 50 MB 和 500,000 行（`MAX_UPLOAD_BYTES` 和 `MAX_ROWS` 变量）。
- 数量为不超过 2,147,483,647 的整数。价格为普通小数（无货币符号、无千位分隔符），小数点前最多 14 位、后最多 4 位。

### 有效示例

将其保存为 `example.csv`。它有三条明细和两个订单；订单 `A-1001` 有两条明细。

```csv
order_id,order_date,product_id,product_name,quantity,unit_price
A-1001,2025-03-01,P-10,Ceramic Mug,2,12.50
A-1001,2025-03-01,P-20,Travel Tumbler,1,24.00
A-1002,2025-03-02,P-10,Ceramic Mug,1,12.50
```

可包含可选 `customer_id`，允许空单元格：

```csv
order_id,order_date,product_id,product_name,quantity,unit_price,customer_id
A-1001,2025-03-01,P-10,Ceramic Mug,2,12.50,CUST-007
A-1001,2025-03-01,P-20,Travel Tumbler,1,24.00,
```

应用在端口 8000 运行时，通过 API 导入：

```sh
curl -F currency=USD -F file=@example.csv http://localhost:8000/api/datasets
```

响应为 `201`，包含 `"warnings":[]`、`dataset_id`、`token` 和首个摘要。此处总销售额为 61.50，来自 2 个订单和 4 件商品。

### 无效示例

每项都是对有效文件的小改动。应用返回 `422`、错误码 `validation_failed` 和错误列表；每个错误的 `code` 如下表，并带行号和列。

| 对有效文件的改动 | 错误 `code` | 行 |
| --- | --- | --- |
| 从表头删除 `unit_price`（并删除每行最后一个值） | `missing_column` | 无（文件级） |
| 将日期 `2025-03-02` 改为 `2025-13-02` | `invalid_date` | 4 |
| 将最后一行数量从 `1` 改为 `0` | `invalid_quantity` | 4 |
| 重复最后一行 | `duplicate_line` | 5 |

### 错误代码

报告列出前 100 个错误和总数（`error_count`）。

| 代码 | 原因 |
| --- | --- |
| `file_too_large` | 文件大于 `MAX_UPLOAD_BYTES`。 |
| `empty_file` | 文件为空。 |
| `invalid_encoding` | 文件不是有效 UTF-8。 |
| `malformed_csv` | 文件无法读取为 CSV（例如单字段超过 131,072 个字符）。 |
| `too_many_rows` | 数据行超过 `MAX_ROWS`。 |
| `no_data_rows` | 有表头但没有数据行。 |
| `missing_column` | 表头缺少六个必需列之一。 |
| `duplicate_column` | 必需列在表头出现多次。 |
| `missing_value` | 必需值为空。 |
| `invalid_date` | `order_date` 不是以 `YYYY-MM-DD` 书写的真实日期。 |
| `future_date` | `order_date` 晚于今天（UTC）。 |
| `invalid_quantity` | `quantity` 不是 1 到 2,147,483,647 的整数。 |
| `invalid_price` | `unit_price` 不是小数点前 14 位、后 4 位以内的普通小数。 |
| `negative_price` | `unit_price` 小于零。 |
| `line_total_too_large` | `quantity × unit_price` 大于等于 100,000,000,000,000，超出总销售额所用精确小数范围。 |
| `malformed_row` | 该行值数量与表头不同。 |
| `duplicate_line` | 相同 `order_id` 和 `product_id` 已在先前行出现。 |
| `conflicting_product_name` | 一个 `product_id` 有多个 `product_name`。 |
| `conflicting_customer_id` | 一个订单有多个非空 `customer_id`。 |
| `customer_id_too_long` | 非空 `customer_id` 超过 `CUSTOMER_ID_MAX_LENGTH` 个 Unicode 字符。 |
| `customer_id_looks_like_email` | 非空 `customer_id` 匹配明显邮箱启发式。 |
| `customer_id_looks_like_phone` | 非空 `customer_id` 匹配明显电话启发式。 |

三项 `customer_id` 检查只是尽力而为的防护，并非匿名化或合规保证。邮箱检查在值中查找 `[^@\s]+@[^@\s]+\.[A-Za-z]{2,}`。电话检查只允许数字、空格、`+ - . ( )`，要求 7–15 位数字，并且有前导 `+`、可见空格/括号或至少两个 `-`/`.` 分隔符。启发式有意保留已知漏检：`05321234567` 这样的全数字电话会接受，而 `2024-01-000123` 这样有两个连字符的数字组会拒绝。ID 被接受并不表示匿名。

请求也可能在读取文件前失败：不在列表中的货币返回 `400 invalid_request`。

### 客户覆盖率

存在 `customer_id` 时，导入期间会在订单级计算一次覆盖率，先用同一订单另一行的 ID 填充空值：

`identified distinct orders / all distinct orders`

它不是行百分比，因此一个有五行的已识别订单只计一次。数据集元数据报告计数和四舍五入比率，而等级按整个数据集的精确整数计数决定：

- 低于 50%：`suppressed`；客户分析不可用；
- 50% 至不足 80%：`warning`；客户分析可用并显示低覆盖警告；
- 80% 或以上：`normal`；客户分析正常可用。

没有 `customer_id` 的文件等级为 `missing`，且 `coverage: null`，而非零覆盖。覆盖元数据只含计数，不含客户标识符。日期范围覆盖使用相同订单级公式及包含边界的订单日期；空范围计数为零且 `coverage: null`。等级仍以完整数据集为准，因此筛选日期不会使客户模块出现或消失。

### 客户 API

`GET /api/datasets/{id}/customers` 受 bearer 令牌保护，接受与概览、产品模块相同的可选 `start`、`end`、`comparison` 查询参数。无参数时使用完整数据集和默认 `previous_period` 比较。无效日期、反向或范围外日期返回 `400 invalid_range`；未知比较返回 `400 invalid_request`。凭据缺失或格式错误返回 `401 unauthorized` 和 `WWW-Authenticate: Bearer`；未知、过期或已删除数据集返回 `404 not_found`。

类型化响应含 `module`、`range`、`comparison`、`currency`、`availability`、`coverage` 和 `sections`。`coverage.dataset` 为存储的完整数据集覆盖，`coverage.range` 为所选包含边界范围覆盖；两者均含等级、四舍五入比率以及已识别、未识别和总订单计数。覆盖正常或警告时，`sections.identified_customers` 报告包含边界范围内有活动的不同已识别客户，以及共享比较值和变化字段。空活动群体状态为 `zero_result`。`sections.new_vs_returning` 将范围内已识别总销售额拆为新客户销售（客户首次购买日期上的明细）和回访客户销售（后续明细），并含相同比较字段；分类始终使用完整上传历史的 `first_order_date`，因此移动范围开始日不会把回访客户变为新客户。

`sections.days_between_purchases` 仅报告当前范围的复购时间（无比较字段）。各已识别客户的不同订单按首条明细日期排序；每对相邻订单构成一个日历日间隔，同日两个订单为 `0`。若后一个订单在包含边界范围内，则间隔计入，即使前一个订单早于范围开始；范围结束后的订单忽略。返回 `median_days`（偶数数量时取两个中间值的均值，因此可为 `.5`；不报告平均数）、`interval_count`、`contributing_customers` 和九个固定 `buckets`（`0`、`1-7`、`8-14`、`15-30`、`31-60`、`61-90`、`91-180`、`181-365`、`366+` 天），每个桶含 `interval_count` 和占全部间隔的 `share`。无计入间隔时中位数和所有份额为 `null`，状态为 `insufficient_data`。

`sections.cohort_retention` 是仅针对当前范围的月度获客同期群留存矩阵（无比较字段）。客户同期群是完整历史首次订单所在月份；行从包含范围开始日的月份到包含结束日的月份，按最早优先，因此只移动开始日不会改变行。范围结束日为 `data_cutoff`：之后首次出现的客户不属于成员，之后活动忽略，开始日前活动仍计入。每行含 `cohort_month`（`YYYY-MM`）、`cohort_size`、`complete_months`、`cells`；第 `N` 月（0 = 获客月）含 `retained_count`（该日历月有已识别明细的成员）和 `retention`（`retained_count / cohort_size`）。每个单元格的 `state` 为 `complete`（整月不晚于截止日）、`partial`（该月包含截止日；统计迄今）或 `not_observed`（该月始于截止日后；值为 `null`，绝非 `0`）。各行填充至与最老同期群等宽。没有重叠同期群时 `rows` 为空，状态为 `insufficient_data`。

`sections.historical_customer_value` 报告仅针对当前范围、已观察到的历史客户价值（已观察总销售额，不是预测）。群体为 `cohort_retention` 各行成员；客户价值为截至 `data_cutoff`（范围结束日）的已识别总销售额，包括范围开始前销售。返回 `customer_count`、`average`（总价值 / `customer_count`）和 `median`（偶数数量取两个中间值均值），金额按 half-up 四舍五入至 4 位小数。`rows` 映射 `cohort_retention` 的行和单元格状态，每个单元格 `value_per_customer` = 该同期群截至第 `N` 月末的累计总销售额（不超过截止日）/ `cohort_size`（`not_observed` 时为 `null`）。`all_cohorts` 对单元格为 `complete` 的同期群按每个月偏移生成一个点（`value_per_customer`、`contributing_cohorts`；无完整单元格时为 `null` 和 `0`）。无同期群时状态为 `insufficient_data`；成员总价值为 0 时，以 `0.0000` 值返回 `zero_result`。

`sections.rfm` 仅报告当前范围的 RFM 分群计数，无比较。群体（`customer_count`，N）是范围结束日前有已识别订单的客户；计入截至结束日的所有已识别活动，范围开始日无影响。最近购买为客户最新已识别明细到 `recency_anchor`（范围结束日）的天数；频率为不同订单数；金额为总销售额。各维度按客户排名获得 1-5 分：`floor(5 × (2 × worse + ties) / (2 × N)) + 1`，其中 `worse` 为值严格更差的客户数，`ties` 为相同值客户数，因此相等值得同分，恒定维度得 3 分。令 `FM = F + M`，首条匹配规则决定分群：Champions (R ≥ 4, FM ≥ 8)、Loyal (R ≥ 3, FM ≥ 6)、Potential Loyalists (R ≥ 4, FM ≤ 5)、Needs Attention (R = 3, FM ≤ 5)、At Risk (R ≤ 2, FM ≥ 6)、Lost (R ≤ 2, FM ≤ 5)。`segments` 始终以该顺序列出全部六类，含 `customer_count` 和 `share`；逐客户分数永不离开后端。少于 5 名客户时 `segments` 为空且为 `insufficient_data`。固定 `note` 说明分群相对于本次上传的客户群，而非通用基准。

`sections.rfm_drilldown` 按 RFM 分群报告聚合数值，与 `sections.rfm` 使用相同群体、输入和分群，且无比较。顶层返回 `customer_count`（N，与 `sections.rfm` 相同）、`recency_anchor`（范围结束日）、`gross_sales`（截至结束日 N 名客户的金额总和，half-up 到 4 位小数）。`segments` 始终按 `sections.rfm` 顺序列出六类；各自含 `customer_count`、`gross_sales`（成员金额总和）、`gross_sales_share`（分群 `gross_sales` / 顶层 `gross_sales`；总额为 `0` 时为 `null`）、六个距锚点天数固定桶的 `recency_distribution`（`0-30`、`31-60`、`61-90`、`91-180`、`181-365`、`366+`；含 `key`、`min_days`、`max_days`、`customer_count`），以及八个不同订单数固定桶的 `frequency_distribution`（`1`、`2`、`3`、`4`、`5`、`6-10`、`11-20`、`21+`；含 `key`、`min_orders`、`max_orders`、`customer_count`）。开放桶最大值为 `null`，空分群和桶为 `0`。单成员分群与其他分群一样报告，因为不返回客户标识符或分数。少于 5 名客户时以真实 `customer_count`、`gross_sales` 和空 `segments` 返回 `insufficient_data`。

覆盖缺失或被抑制时，所有章节都省略（`sections` 为空）。端点始终返回 `Cache-Control: no-store`。客户响应设计上仅含聚合数据：绝不返回客户标识符、客户级对象、搜索、详情、下载或导出数据，且标识符不写入日志。

### 警告

警告不会拒绝文件。它们会出现在 `201` 响应的 `warnings` 列表和上传页面上。

| 代码 | 含义 |
| --- | --- |
| `extra_column` | 文件含不属于六个必需列或 `customer_id` 的列，例如 `note` 列；该列忽略且不存储。 |
| `zero_price` | 一条或多条明细单价为 0；仍会导入并计为订单和件数，但没有总销售额。 |

### 样例数据

从 <http://localhost:8000/api/sample.csv> 下载有效样例文件（上传页面以**下载示例 CSV**链接）。上传页面的**试用示例数据**无需上传即可用 USD 导入同一文件。

## 趋势分桶

趋势按日历桶汇总总销售额。粒度只取决于选定范围并包含首尾日期：最多 90 天按日；超过 90 天至 730 天按周；更长按月。API 为每个桶返回 `bucket_start`（桶首日），不返回覆盖字段。

- 范围包含边界：开始日和结束日均在其中。
- 周从星期一至星期日；周桶的 `bucket_start` 为星期一。月为日历月。
- 被范围截断的桶（首周/月始于开始日前，末周/月结束于结束日后）是部分周期。图表根据范围和日历计算，即使某日无销售也算覆盖。单日的日桶始终完整（数据只存日期）；周或月的一日切片为部分周期。位于同一周或月内的范围会把该桶显示为部分周期。
- 部分周期的显示：部分周/月的轴标签显示其覆盖日期（`29–12月31日`、`10–2025年3月31日`），而非 `12月29日所在周` 或月份名；数据点为空心；图下有说明；工具提示加年份和 `部分期间: <覆盖日期>`。完整桶没有这些标记。
- 只汇总范围内的行，因此部分桶只含其覆盖日期的销售额。

## 货币

在上传表单选择货币：USD、EUR、GBP、TRY、CAD、AUD、JPY、CHF、SEK、PLN。它只是金额标签，不进行换算，也没有汇率。其他代码均以 `400 invalid_request` 拒绝。

## 隐私

- 无论成功或失败，导入结束后立即删除原始 CSV。
- 必需列和可选 `customer_id` 存储在 `DATASET_DIR` 下每数据集一个 DuckDB 文件中，并使用私有权限（文件 `0600`，目录 `0700`）。
- 客户 ID 是假名化而非匿名数据，在数据集 24 小时生命周期内保留。使用哈希标识符、UUID 或非个人内部键；切勿上传邮箱、电话号码或姓名等直接标识符。
- 客户 ID 长度、邮箱和电话检查仅为尽力而为的防护，不是匿名化或合规保证；自动检查无法发现所有个人数据。
- 数据集在 `DATASET_TTL_HOURS`（默认 24）后由启动时及之后每 `CLEANUP_INTERVAL_MINUTES` 一次的清理删除，或在单击**分析另一个文件**时立即删除。
- 成功的模块响应可在有界的进程本地缓存中保留 `RESPONSE_CACHE_TTL_SECONDS`（默认 300 秒）；每个请求都授权，条目按数据集和选项区分，过期或删除会移除缓存响应。实例间不共享缓存。
- 访问需要随机 bearer 令牌。浏览器保存在 `sessionStorage`，标签页关闭即消失。服务器只保存其 SHA-256 哈希。
- 缺失或过期的数据集 ID 返回 404，现有数据集使用错误令牌返回 401，因此状态会透露 ID 是否存在。这是已接受风险：ID 为不可猜测的 128 位随机值，没有令牌仍无法读取数据集。
- 日志每请求一行 JSON，含方法、路径、状态、耗时和数据集 ID。为追踪请求会特意记录数据集 ID；它不是秘密，且没有令牌无法使用。日志绝不含令牌、文件内容、文件名、产品名或订单 ID。错误日志只含异常类名和堆栈帧，不含异常消息。
- 不向其他服务发送任何内容。
- 提供客户 ID 时，每数据集 DuckDB 文件还含 `customer_facts`：每个已识别客户一行，含完整历史的首次/末次订单日期、获客月、不同生命周期订单、件数和总销售额。未识别订单没有对应行；它随数据集过期，并非独立共享数据库。

## 演示模式

托管演示是以 `PUBLIC_DEMO_MODE=true` 运行的公开实例：访客只能探索内置样例数据，不能上传文件。其数据集与其他数据集一样过期（`DATASET_TTL_SECONDS`），并以单实例运行。要分析自己的文件，请[自行运行](#使用-docker-运行)。

`PUBLIC_DEMO_MODE=true` 用于不应接收他人文件的公共服务器：

- `POST /api/datasets` 不读取正文并返回 403 `upload_disabled`。
- **试用示例数据**和样例下载仍可使用。
- 上传页面只显示文件格式和**试用示例数据**，没有文件或货币字段。页面说明只接受样例数据，并链接到[使用 Docker 运行](#使用-docker-运行)以便上传。
- `GET /api/config` 返回 `{"public_demo_mode":true,...}`，页面据此判断。
- `MAX_DATASETS` 保护公共服务器磁盘：每次单击**试用示例数据**都创建数据集，达到上限时返回 503 `capacity_reached`。

## 限制

- 仅单实例，不支持水平扩展：数据集是该实例磁盘上的文件。
- 重启后保留属于尽力而为，且仅在 `DATASET_DIR` 位于卷上时有效。
- 无账户和共享。数据集只能用其令牌访问，而令牌保留在单个浏览器标签页中。
- 每个文件一种货币。
- 不提供客户级列表、导出或搜索；客户数值仅涵盖已识别订单。
- 仅总销售额：不含退款、折扣、税费或运费。
- 默认 50 MB 和 500,000 行。
- 支持手机、平板和桌面宽度（360 px 起）；宽表格在其自身区域内滚动（参见 [`_docs/design-system.md`](_docs/design-system.md)）。

## 路线图

第 3 阶段已完成。下一批候选项来自[第 3 阶段规范](_docs/open_sales_analytics_phase_3_spec.md#20-deferred-roadmap)：

- **第 4 阶段：托管产品基础。** 中央应用数据库、账户、所有权、已保存数据集和持久仪表板。
- **第 4 阶段：托管数据摄取。** 带速率限制、隔离、滥用控制和监控的受保护公开上传。
- **第 4 阶段：财务契约层。** 可选 `discount_amount`、`refund_amount`、`unit_cost` 列，以及净销售额、折扣、退款和利润分析。
- **未来：** Shopify、WooCommerce 和市场格式映射器；多文件和多渠道数据集；具有明确隐私模型的客户激活与导出；更大规模异步导入；只有在验证用户需求后才加入预测或异常检测。

## 架构

React（Vite）前端通过 JSON 与 FastAPI 后端通信。每个数据集是 `DATASET_DIR` 下的一个 DuckDB 文件；验证和分析均以 SQL 对该文件执行。规范导入会在同一文件中构建可复用的 `order_facts`、`product_facts`，并在有已识别客户数据时构建完整历史 `customer_facts`。进程内后台任务删除过期数据集。Docker 镜像为单容器，FastAPI 从同一源的端口 8000 同时提供 API 和构建后的前端。参见[第 3 阶段架构指南](_docs/architecture.zh-CN.md)、[指标目录](_docs/metrics.zh-CN.md)、[发布检查表和证据报告](_docs/phase-3-release-checklist.md)、[第 3 阶段规范](_docs/open_sales_analytics_phase_3_spec.md)和[待办事项](_docs/tasks.md)。

## 开发

工作组织方式：[`_docs/process.md`](_docs/process.md)。测试约定：[`_docs/testing-guidelines.md`](_docs/testing-guidelines.md)。性能基线命令和结果：[`_docs/benchmarks.md`](_docs/benchmarks.md)。

在存储库根目录运行：

```sh
uv sync
uv run pytest
```

Lint 和类型检查（与 CI 相同；`uv sync` 将 `ruff` 和 `mypy` 安装为开发依赖）：

```sh
uv run ruff check backend
uv run ruff format --check backend   # `uv run ruff format backend` fixes it
uv run mypy backend/app
```

依赖扫描（与 CI `dependency-scan` 作业相同；`uvx` 运行 `pip-audit` 而不把它加入项目依赖）：

```sh
uv export --locked --no-emit-project --format requirements-txt -o /tmp/requirements.txt
uvx pip-audit@2.10.1 -r /tmp/requirements.txt --no-deps --disable-pip
(cd frontend && npm audit --audit-level=high)
```

启动后端（在 http://127.0.0.1:8000 提供服务）：

```sh
uv run uvicorn app.main:app --app-dir backend
```

检查：`curl http://127.0.0.1:8000/api/health` 返回 `{"status":"ok"}`。要在不使用 Docker 时从同一源提供构建后的前端，先在 `frontend/` 中运行 `npm run build`（见下文），再按上面方式启动后端并打开 <http://127.0.0.1:8000>。

### 前端

需要 Node 22 或更高版本。在 `frontend/` 中：

```sh
npm ci            # install
npm run dev       # dev server on http://localhost:5173
npm test          # Vitest, single run
npm run lint      # ESLint
npm run typecheck # tsc --noEmit (TypeScript 7)
npm run build     # type check, then the production bundle in frontend/dist
```

`npm run dev` 将 `/api` 代理到端口 8000 的后端，因此也需启动后端。

### 必需的 CI 检查

合并到 `main` 应要求以下四项检查，其拼写必须与 GitHub 拉取请求显示完全相同（Settings、Branches 或 Rules、"Require status checks to pass"，然后选择各名称）：

- `Backend (tests, ruff, mypy)`
- `Frontend (tests, lint, type check, build)`
- `Dependency scan (Python, npm) / Dependency scan (Python, npm)`
- `Container (build, smoke, browser tests)`

依赖扫描调用可复用工作流 `.github/workflows/dependency-scan.yml`，而 CI 定义位于 `.github/workflows/ci.yml`，所以 GitHub 以 `<calling job> / <called job>` 形式将名称显示两次。在分支保护中选择完整的双重名称；单独的 `Dependency scan (Python, npm)` 不匹配检查运行。若重命名 `.github/workflows/` 中的作业，应在同一更改中更新此列表和保护设置，因为不存在的必需检查会阻止所有合并。可在任意拉取请求上用 `gh pr checks <number>` 比较。

### 依赖扫描

CI 在每个拉取请求、每次推送到 `main` 时扫描两个锁文件，并于每周一 05:17 UTC 再扫描（`.github/workflows/dependency-scan-scheduled.yml`），因此未更改锁文件中新出现的公告会在下个拉取请求前令运行变红。两者都调用 `.github/workflows/dependency-scan.yml` 中的同一定义，所以命令和策略一致。计划运行仅有 `contents: read`、没有秘密，也可从 Actions 标签页用“Run workflow”手动启动。

| 生态系统 | 工具和输入 | 导致 CI 失败的条件 |
| --- | --- | --- |
| Python | 对 `uv.lock`（运行时与开发包）运行 `pip-audit` | 任何已知漏洞（pip-audit 无严重性筛选） |
| npm | 对 `frontend/package-lock.json` 运行 `npm audit --audit-level=high` | 高危与严重公告；低危和中危会显示但不失败 |

扫描器出错（无网络、输入错误）也会让作业失败；步骤没有 `|| true` 或 `continue-on-error`。没有忽略列表。若公告尚无修复，解决方式是经审查的拉取请求：在扫描命令旁写明公告 ID 和理由并固定例外（`pip-audit --ignore-vuln ID`），或移除包；绝不静默跳过。缓存只保存包下载和 Playwright 浏览器；不缓存或上传数据集、上传文件、秘密或 DuckDB 文件作为制品。

Dependabot（`.github/dependabot.yml`）每周一为过时的 Python（`uv.lock`，来自 `pyproject.toml`）和 npm（`frontend/package-lock.json`）依赖创建拉取请求，每个生态最多 5 个打开项。Dependabot 只升级现有依赖，绝不新增依赖。其拉取请求执行相同 CI 且没有秘密（使用只读令牌），因此依赖扫描、测试、构建和浏览器套件都在更新后的锁文件上运行。审查方式与其他更改相同：阅读发行说明和锁文件差异，只有所有检查为绿色时才合并；大版本升级还需手动运行一次应用。红色检查意味着关闭或修复拉取请求，绝不能合并。

计划运行失败会在存储库 Actions 标签页显示名为“Dependency scan (scheduled)”的红色运行（按工作流名称或 `event:schedule` 筛选）。GitHub 也会向存储库所有者发送邮件：计划工作流通知最后修改 `cron` 行的用户，因此若其他人改动计划，应确认其通知设置（Settings、Notifications、Actions）已开启。计划工作流只在默认分支运行；存储库 60 天无活动后 GitHub 会暂停它，应从 Actions 标签页重新启用。

### 容器镜像固定

决定：`Dockerfile` 中基础镜像（`node:26`、`python:3.14-slim`）按摘要固定（`FROM image:tag@sha256:...`，多架构索引摘要）。原因：标签会移动，同一提交的两次构建可能不同，未经审查的上游变化可能破坏或危及构建；摘要使构建可复现，且每次基础镜像变化都经过拉取请求审查。Dependabot（`.github/dependabot.yml` 的 `docker` 项，每周一）同时更新标签和摘要，`docker-smoke` CI 作业会在合并前构建并启动新镜像。手动更新时，查找所需标签摘要并替换 `FROM` 行两部分。用 `COPY --from=ghcr.io/astral-sh/uv:0.8` 复制的 `uv` 镜像目前仍使用标签。

### 固定 Actions

若 `.github` 下任何 `uses:` 既不是本地路径（`./.github/workflows/...`），也不是 `owner/repo@<40 hex characters>`，`pinned-actions` 作业会失败；错误注释指出文件和行。固定格式为 `uses: owner/repo@<sha> # vX.Y.Z`；Dependabot 保持 SHA 和注释为最新。该检查是具有 `contents: read` 的 shell 步骤，除 `actions/checkout` 外没有秘密或第三方 Action，因此也会在 fork 和 Dependabot 的拉取请求中运行。

### 浏览器测试

小型 Playwright 套件（Chromium，`frontend/e2e/`）涵盖主要流程：试用示例数据、有效上传、无效上传、日期范围与重置、分析另一个文件、跨模块客户流程、360/768/1280 px 响应式布局以及过期数据集。
浏览器只需安装一次（约 150 MB，存储库外），然后从 `frontend/` 运行：

```sh
npx playwright install chromium
npx playwright install-deps chromium   # Linux only: system libraries, needs sudo; CI runs it too
npm run e2e
```

`npm run e2e` 会自行启动后端（端口 8000）和 Vite 开发服务器（端口 5173），使用临时数据集目录，完成后停止。两个端口必须空闲。若测试已运行应用（如容器），设置 `E2E_BASE_URL`，便不启动服务器。该应用必须使用 `DATASET_TTL_SECONDS=60`，因为过期流程会通过有界轮询等待真实过期：

```sh
docker build -t open-sales-analytics .   # from the repository root
docker run -d --name oca -p 8000:8000 -e DATASET_TTL_SECONDS=60 open-sales-analytics
curl -f http://localhost:8000/api/health   # answers {"status":"ok"}; repeat for a few seconds until it does
curl -f http://localhost:8000/d/anything | grep -i '<div id="root"'   # the single-page app
E2E_BASE_URL=http://localhost:8000 npm run e2e
docker rm -f oca
```

失败时，跟踪和截图保存在 `frontend/test-results/`（用 `npx playwright show-trace` 打开跟踪）。设置 `CI` 时（如 GitHub Actions）不记录跟踪，因为其中含网络响应，CI 只上传失败截图。

## 贡献

欢迎错误报告、想法和拉取请求；参见 [`CONTRIBUTING.md`](CONTRIBUTING.zh-CN.md)。

## 许可证

按 [Apache License, Version 2.0](LICENSE) 授权。
