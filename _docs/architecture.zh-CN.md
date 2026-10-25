# 架构

语言：[English](architecture.md) | [Türkçe](architecture.tr-TR.md) | [Deutsch](architecture.de-DE.md) | [Русский](architecture.ru-RU.md) | [Español](architecture.es-ES.md) | [简体中文](architecture.zh-CN.md) | [日本語](architecture.ja-JP.md)

> 本译文以[英文原文](architecture.md)为准；同步修订版本 `045796b0c7bbdd21520ccce1c7972495aab929f8`，同步日期 `2026-10-22`。

Open Sales Analytics 是由 FastAPI 提供服务的同源 React/Vite 应用。前端将数据集标识符和 bearer 令牌保存在单个浏览器标签页的 `sessionStorage` 中；它把日期范围和比较选项发送到后端，并呈现聚合响应。除每个数据集对应的一个 DuckDB 文件以及有界的进程内响应缓存外，后端在请求之间无状态。

## 存储库领域

| 领域 | 实际路径 | 职责 |
| --- | --- | --- |
| API 与生命周期 | `backend/app/api/`, `backend/app/auth.py`, `backend/app/cleanup.py` | 上传/样例创建、授权、过期、元数据和响应封装 |
| 概览 | `backend/app/analytics/overview/` | 总销售额、不同订单数、件数、平均订单价值、趋势和比较 |
| 产品 | `backend/app/analytics/products/` | 排名、份额/Pareto、增长、休眠、价格历史、订单渗透率和购物篮关联 |
| 客户 | `backend/app/analytics/customers/` | 覆盖率、客户聚合、同期群、RFM 和预测 |
| 共享周期和可用性 | `backend/app/analytics/shared/` | 包含边界的日期筛选、比较周期、分桶选择、可用性和指标定义 |
| 导入和持久化 | `backend/app/ingest.py`, `backend/app/importer.py`, `backend/app/schema.py` | 验证 CSV、构建事实表、写入数据集文件并删除暂存数据 |
| Web UI | `frontend/src/` | 上传、仪表板导航、无障碍状态、表格和图表文本替代内容 |

权威指标公式和状态位于 `backend/app/analytics/shared/metrics.py`；便于阅读的目录见 [_docs/metrics.md](metrics.zh-CN.md)。第 3 阶段产品规范见 [_docs/open_sales_analytics_phase_3_spec.md](open_sales_analytics_phase_3_spec.md)。

## 数据集文件

每次上传都会在 `DATASET_DIR` 下生成一个私有 DuckDB 文件。导入时只计算一次可复用事实；请求时的查询会按选定的包含边界范围和比较周期筛选这些事实。

| 表 | 列 | 含义 |
| --- | --- | --- |
| `line_items` | `order_id`, `order_date`, `product_id`, `product_name`, `quantity`, `unit_price`, nullable `customer_id` | 已验证的源行；每个产品行一条记录，可含不透明的可选客户 ID |
| `order_facts` | `order_id`, `first_order_date`, `last_order_date`, `line_count`, `units`, `gross_sales` | 每个订单一行，包含其生命周期行数/订单总计 |
| `product_facts` | `product_id`, `product_name`, `first_sale_date`, `last_sale_date`, `lifetime_gross_sales`, `lifetime_units`, `lifetime_orders` | 每个产品一行，包含生命周期产品组合事实 |
| `customer_facts` | `customer_id`, `first_order_date`, `acquisition_month`, `first_day_orders`, `last_order_date`, `lifetime_orders`, `lifetime_units`, `lifetime_gross_sales` | 每个已识别客户一行；六列数据中不存在或为空 |
| `dataset_meta` | `id`, `currency`, `created_at`, `expires_at`, `token_hash`, `row_count`, `has_customer_id`, `identified_orders`, `unidentified_orders`, `total_orders` | 数据集身份、生命周期、保护隐私的令牌验证和覆盖计数 |

原始上传字节仅在验证/导入期间暂存，并在导入完成后删除。派生表随数据集一起删除。客户事实只含假名化 ID，绝不会以客户列表形式返回。

## 请求流程

1. `POST /api/datasets` 验证 multipart CSV、应用逐行及跨行规则、创建 DuckDB 事实表，仅存储 SHA-256 令牌哈希，并返回数据集 ID、一次性令牌、元数据和初始概览。
2. `require_dataset` 在模块处理器运行前验证 bearer 标头、数据集 ID、文件可读性、过期时间和令牌。每次请求都执行授权，包括缓存命中。
3. 处理器解析包含边界的活动范围和比较模式，构建缓存键，然后返回成功缓存的 JSON 正文，或以只读方式打开数据集并计算模块响应。
4. 响应为仅含聚合数据的 JSON。缓存只存储成功的序列化正文；其键包含数据集 ID、模块、活动日期、比较模式和模块选项。
5. 数据集过期、显式删除和清理扫描会使该数据集的缓存条目失效。缓存属于进程本地、线程安全且受 LRU 大小限制，条目会在缓存 TTL 与数据集过期时间中较早者到达时过期。

## API 表面

除公开的健康检查、配置和样例下载路由外，所有数据集路由都需要 `Authorization: Bearer <token>`。在线 OpenAPI 模式是权威来源；`backend/tests/test_documentation.py` 会对照它检查此表。

| 方法 | 路径 | 授权 | 用途和主要选项 |
| --- | --- | --- | --- |
| GET | `/api/health` | 否 | 旧版健康响应 |
| GET | `/health/live` | 否 | 仅检查进程存活，不检查依赖项 |
| GET | `/health/ready` | 否 | 就绪状态和安全的服务标识 |
| GET | `/api/config` | 否 | 公开演示标志和上传限制；绝不含秘密或路径 |
| POST | `/api/datasets` | 否 | Multipart 上传；`currency` 表单字段 |
| POST | `/api/datasets/sample` | 否 | 以 USD 导入内置样例 |
| GET | `/api/sample.csv` | 否 | 下载内置样例 CSV |
| GET | `/api/datasets/{id}` | 是 | 数据集元数据、能力、覆盖率和过期时间 |
| GET | `/api/datasets/{id}/analytics` | 是 | 旧版概览摘要；可选 `start`, `end` |
| DELETE | `/api/datasets/{id}` | 是 | 删除数据集并使其缓存失效 |
| GET | `/api/datasets/{id}/overview` | 是 | 概览 KPI 和趋势；`start`, `end`, `comparison` |
| GET | `/api/datasets/{id}/products` | 是 | 产品组合分析；`start`, `end`, `comparison`, `dormancy_days` |
| GET | `/api/datasets/{id}/products/detail` | 是 | 产品详情；`product_id`, `start`, `end`, `comparison` |
| GET | `/api/datasets/{id}/customers` | 是 | 客户聚合和预测；`start`, `end`, `comparison` |

## 部署形态

Docker 镜像在 Node 阶段构建前端，用 `uv` 安装后端环境，并运行一个 FastAPI 进程。FastAPI 从端口 8000 提供构建后的 SPA 和 `/api`。若数据集必须在重启后保留，`DATASET_DIR` 应为私有持久卷；系统没有共享数据库或水平扩展层。
