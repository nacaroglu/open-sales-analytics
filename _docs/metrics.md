# Metric catalogue

Languages: [English](metrics.md) | [Türkçe](metrics.tr-TR.md) | [Deutsch](metrics.de-DE.md) | [Русский](metrics.ru-RU.md) | [Español](metrics.es-ES.md) | [简体中文](metrics.zh-CN.md) | [日本語](metrics.ja-JP.md)

This catalogue follows `backend/app/analytics/shared/metrics.py`. All ranges are inclusive. “Unavailable” means the
module cannot answer for the file or comparison; “insufficient data” means the metric's threshold is not met; a
“zero result” is a valid answer with no matching rows. The measure is always **gross sales**, never revenue.

| Key | UI name | Formula / numerator | Denominator | Window, anchor and caveat |
| --- | --- | --- | --- | --- |
| `first_purchase` | First purchase | Earliest order date across full history | — | Full uploaded history; no identified order means unavailable |
| `acquisition_cohort` | Acquisition cohort | Calendar month containing first purchase | — | Full history; month is represented by its first day |
| `gross_sales` | Gross sales | `SUM(quantity × unit_price)` | — | Active range; no sales returns 0 |
| `orders` | Distinct orders | `COUNT(DISTINCT order_id)` | — | Active range; no orders returns 0 |
| `units_sold` | Units sold | `SUM(quantity)` | — | Active range; no units returns 0 |
| `average_order_value` | Average order value | Gross sales | Distinct orders | Active range; no orders returns 0 |
| `change_percent` | Percentage change | `(current - comparison) / comparison × 100` | Comparison value | Selected comparison; zero baseline uses a worded status and absolute change |
| `product_revenue_share` | Gross-sales share | Product gross sales | Total gross sales | Compatibility key; active range; unavailable when total is zero |
| `gross_sales_share` | Gross-sales share | Product gross sales | Total gross sales | Active range; unavailable when total is zero |
| `cumulative_share` | Cumulative gross-sales share | Running product gross sales | Total gross sales | Descending product order; unavailable when total is zero |
| `top_20_percent_share` | Top 20% product share | Gross sales of first `ceil(0.2 × product_count)` products | Total gross sales | Active range; unavailable when total is zero |
| `products_to_80_percent` | Products to 80% of gross sales | Smallest qualifying product prefix | Total gross sales | Active range; unavailable when total is zero |
| `product_growth` | Product gross-sales growth | Current gross sales minus comparison gross sales | — | Selected comparison; unavailable when baseline is unavailable |
| `rising_products` | Rising products | Count with positive gross-sales change | — | Selected comparison; signs and words are shown, not colour alone |
| `falling_products` | Falling products | Count with negative gross-sales change | — | Selected comparison; signs and words are shown, not colour alone |
| `new_products` | New products | Present in current, absent in comparison | — | Selected comparison; no comparison means unavailable |
| `no_current_sales_products` | Products with no current sales | Present in comparison, absent in current | — | Selected comparison; no comparison means unavailable |
| `unchanged_products` | Unchanged products | Equal gross sales in both periods | — | Selected comparison; no comparison means unavailable |
| `growth_rank_absolute_change` | Product growth rank | Rank by absolute gross-sales change | — | Selected comparison; tiny baselines do not dominate |
| `dormancy` | Dormant products | Products where anchor minus last sale is at least window | — | Anchor is selected range end; window is 30, 60 or 90 days; history can be insufficient |
| `cumulative_revenue_share` | Cumulative gross-sales share | Running descending product gross sales | Total gross sales | Compatibility key; active range; unavailable when total is zero |
| `weighted_unit_price` | Weighted realized unit price | `SUM(quantity × unit_price)` | `SUM(quantity)` | Daily/weekly/monthly active-range bucket; no units means unavailable; no elasticity claim |
| `order_penetration` | Order penetration | Orders containing product | All orders | Active range; no orders means zero result |
| `basket_support` | Basket support | Shared orders for A and B | Eligible basket orders | At least 10 shared orders and 0.1% support; >100-product orders excluded only here |
| `basket_confidence` | Basket confidence | Shared orders for A and B | Orders containing source product | Same basket thresholds; direction matters |
| `basket_lift` | Basket lift | Directional confidence | Destination product support | Same basket thresholds; compares observed pair rate with destination support |
| `identified_customers` | Identified customers | Distinct identified customer IDs | — | Active range; none is zero result |
| `customer_coverage` | Customer coverage | Identified distinct orders | All distinct orders | Dataset/range order coverage; <50% suppressed, 50–<80% warning, ≥80% normal |
| `new_vs_returning` | New versus returning customer gross sales | Identified gross sales split by first full-history order date | — | Active range; first-order anchor uses complete history |
| `repeat_purchase` | Repeat-purchase rate | Active customers with ≥2 distinct orders through end | Active identified customers | Orders before range start count; no active customer is insufficient |
| `days_between_purchases` | Days between purchases | Median of consecutive identified order-date intervals | — | Later order must be in range; same-day interval is 0; fixed inclusive buckets |
| `cohort_retention` | Cohort retention | Retained customers in cohort/month offset | Full-history cohort size | Cutoff is selected end; future cells say Not yet observed, never 0 |
| `historical_customer_value` | Historical Customer Value | Observed identified gross sales per customer; median per-customer value | Identified customers | Observed only, no forecast; cohort membership uses full-history acquisition month |
| `projected_customer_value` | Projected 12-Month Customer Value | Observed value plus mature-cohort incremental estimate | Identified customers | Estimate only: 18 months history, 500 customers, 70% coverage, 5 mature cohorts, 12-month horizon |
| `rfm` | RFM segments | Relative recency, frequency and monetary quintile scores; `FM = F + M` | Identified customers | Through selected end; fewer than 5 is insufficient; relative to this upload, not a benchmark |
| `rfm_drilldown` | RFM segment drill-downs | Aggregate segment counts, gross sales and fixed distributions | Segment totals | Aggregate-only; no customer identifiers; same RFM caveat |
| `purchase_frequency` | Purchase frequency | Customers grouped by distinct identified order count | Identified customers through end | Fixed buckets 1, 2, 3, 4, 5, 6–10, 11–20, 21+ |
| `concentration` | Customer concentration | Gross sales of top `ceil(N / 10)` customers | Identified gross sales | Active range; fewer than 10 customers or zero sales is insufficient |

The projection is an estimate, not a guarantee or causal/profit measure. Customer IDs are pseudonymous, not
anonymous; all customer responses are aggregate-only and do not expose lists, search, export or per-customer values.

