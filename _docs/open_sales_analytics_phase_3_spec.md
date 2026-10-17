# Open Sales Analytics — Phase 3 Product Specification and Backlog

**Status:** Scope agreed  
**Date:** 2026-10-17  
**Project:** Open Sales Analytics (OSA)  
**Phase objective:** Turn the existing lightweight dashboard into a portfolio-quality e-commerce analytics engine without turning it into a general-purpose BI platform.

## 1. Executive Summary

Phase 3 deepens Open Sales Analytics in two focused directions:

1. **Customer Intelligence — primary story:** Are customers returning, and which customer groups create durable value?
2. **Product Intelligence — secondary story:** Which products are growing, declining, dormant, or commonly purchased together?

The application remains a generic, CSV-first e-commerce analytics tool. It is not Shopify-specific, does not add a managed SaaS control plane, and does not migrate to Superset.

Phase 3 preserves the existing six required CSV columns and adds only one optional field: `customer_id`. Files without that field continue to receive Overview and Product analytics. Customer analytics becomes available when usable customer data is present.

The work will be delivered as three explicit increments:

| Increment | Name | Outcome |
| --- | --- | --- |
| **3A** | Product Intelligence | Shared analytics foundation, comparisons, product diagnostics and basket analysis |
| **3B** | Customer Intelligence | Optional customer contract, retention, cohorts, RFM and customer diagnostics |
| **3C** | Predictive & Polish | Transparent 12-month value projection, performance work and release-quality polish |

## 2. Product Strategy

### 2.1 Primary objective

The primary goal is a **portfolio-quality analytics engine**. Phase 3 should demonstrate:

- precise metric semantics;
- trustworthy handling of incomplete data;
- non-trivial DuckDB SQL;
- clear domain separation;
- explainable cohort, RFM and basket analysis;
- disciplined validation, testing and performance measurement.

The design should preserve a path toward a hosted multi-channel product, but Phase 3 will not build that product prematurely.

### 2.2 Target user

The product persona remains a small e-commerce owner or operator who can export completed order-line data as CSV and wants understandable sales, customer and product insights without adopting a full BI platform.

For Phase 3 itself, a second audience is important: engineers, recruiters and potential contributors evaluating the project as a case study.

### 2.3 Core jobs to be done

**Customer job**

> Help me understand whether customers return, how retention changes by acquisition cohort, which customer segments matter, and what value existing behavior could produce over a defined horizon.

**Product job**

> Help me understand which products drive the business, which are gaining or losing momentum, which have gone dormant, and which products tend to be bought together.

### 2.4 Product principles

- A small number of coherent modules is better than a catalogue of unrelated metrics.
- Every metric must have a documented formula, denominator, time window and insufficient-data state.
- Missing data must be visible; the product must not silently imply completeness.
- Predictions must be labelled as estimates and separated from observed results.
- The existing upload-to-dashboard workflow and self-hosted simplicity must remain intact.

## 3. Phase 3 User Experience

### 3.1 Navigation

The dashboard contains three focused sections:

1. **Overview** — existing sales KPIs and trend, enhanced with period comparison.
2. **Customers** — availability/coverage, retention, cohorts, value, RFM, frequency and concentration.
3. **Products** — rankings, share, growth, dormancy, price history, penetration and basket affinity.

The sections share:

- a global reporting date range;
- a comparison mode;
- dataset currency and metadata;
- consistent loading, empty, warning, unauthorized and expired states.

There is no customizable dashboard builder.

### 3.2 Progressive feature availability

- Overview and Product modules require only the original six columns.
- The Customer module unlocks when `customer_id` is present and coverage is sufficient.
- Each unavailable analysis explains which data or history requirement is missing.
- The UI must distinguish **unavailable**, **insufficient data**, **low coverage**, and **zero result**.

### 3.3 Customer privacy presentation

Customer analytics is aggregate only. RFM drill-downs show segment counts, sales, recency and frequency distributions, but never list or return individual customer identifiers.

## 4. Dataset Contract

### 4.1 Inherited required columns

The existing contract remains unchanged:

| Column | Status | Summary |
| --- | --- | --- |
| `order_id` | Required | Non-empty order identifier |
| `order_date` | Required | ISO date `YYYY-MM-DD`; not in the future |
| `product_id` | Required | Non-empty product identifier |
| `product_name` | Required | Consistent name for each product ID |
| `quantity` | Required | Positive integer |
| `unit_price` | Required | Non-negative decimal; zero produces a warning |

The dataset grain remains one row per completed order line item. `(order_id, product_id)` remains unique. One currency is selected for the complete upload.

### 4.2 New optional column **[3B]**

| Column | Logical type | Rules |
| --- | --- | --- |
| `customer_id` | Opaque string | Optional and nullable. Maximum length defaults to 128 characters. Must not contain obvious direct personal information. |

Guidance should recommend a hashed identifier, UUID, or non-personal internal key. Email addresses, phone numbers, names and other direct identifiers must not be used.

### 4.3 Customer consistency within an order **[3B]**

For all rows sharing an `order_id`:

- if every non-blank `customer_id` is the same, blanks are filled with that value during canonical import;
- if two different non-blank customer IDs occur, the entire upload is rejected;
- if all values are blank, the order remains unidentified and is excluded from customer analytics.

### 4.4 Extra columns

The inherited rule remains: unrecognized columns are ignored with a warning and are not retained. Phase 3 does not introduce column mapping.

### 4.5 Deferred financial layer

`discount_amount`, `refund_amount`, and `unit_cost` are explicitly excluded from Phase 3. They are recorded as a Phase 4 candidate for net sales, discount rate, refund rate and gross-margin analysis.

## 5. Validation and Data Availability

### 5.1 Existing validation policy

Validation remains all-or-nothing for invalid data. The server never silently discards malformed sales rows.

All inherited file, schema, date, numeric, duplicate and product-identity validations continue to apply.

### 5.2 Customer privacy validation **[3B]**

The server performs best-effort checks on non-blank `customer_id` values:

- reject obvious email-address values;
- reject obvious phone-number values;
- reject values exceeding the configured length limit;
- explain that automated checks cannot guarantee removal of all personal data.

This validation is a guardrail, not a compliance or anonymization claim.

### 5.3 Customer coverage **[3B]**

Customer coverage is calculated at order level:

```text
customer_coverage = identified_distinct_orders / all_distinct_orders
```

| Coverage | Behavior |
| --- | --- |
| Below 50% | Suppress Customer analytics and explain why |
| 50%–79% | Show Customer analytics with a prominent low-coverage warning |
| 80% or more | Show Customer analytics normally |

Every Customer response includes the coverage value and the identified/unidentified order counts.

### 5.4 Projection eligibility **[3C]**

Projected 12-Month Customer Value appears only when all conditions hold:

- at least 18 months of order history;
- at least 500 identified customers;
- customer coverage of at least 70%;
- at least five monthly acquisition cohorts with enough maturity to contribute 12-month behavior.

If any condition fails, the UI lists the exact unmet requirements rather than calculating a weak estimate.

### 5.5 Basket-analysis safeguard **[3A]**

Orders containing more than 100 distinct products are excluded from basket analysis only. They remain included in every other metric. The response reports the number of excluded orders.

## 6. Time and Comparison Semantics

### 6.1 Global reporting range

The existing full-dataset default and start/end date filter remain.

### 6.2 Comparison modes **[3A]**

- **Default:** the immediately preceding period of equal length.
- **Optional:** the same calendar period in the previous year, when the dataset contains that history.
- The UI always displays the exact current and comparison dates.
- YoY is shown as unavailable when the required prior-year dates are absent.

Percentage change is calculated as:

```text
change_percent = (current_value - comparison_value) / comparison_value × 100
```

When the comparison value is zero, the product must not display an infinite percentage. It should label the result as **New**, **No prior value**, or **No change**, as appropriate, and show the absolute change.

### 6.3 Customer identity and date filters **[3B]**

Customer first-purchase date is always calculated from the complete uploaded history up to the selected end date. Selecting a later reporting range must not reclassify an existing customer as new.

- The selected range filters activity and revenue.
- Customer identity and acquisition cohort use full prior history.
- Cohort membership remains stable when the reporting start date changes.
- RFM recency is anchored to the selected end date, not the computer's current date.

### 6.4 Historical datasets

Dormancy and other recency measures are anchored to the dataset's latest relevant date or selected end date, not today's date. This keeps synthetic and historical datasets meaningful.

## 7. Overview Metrics **[3A]**

The existing metrics remain:

- gross sales;
- distinct orders;
- units sold;
- average order value;
- automatically bucketed sales trend;
- top products.

Phase 3 adds comparison values and absolute/percentage deltas using the rules in Section 6. Overview remains concise and does not absorb Customer or Product detail charts.

## 8. Product Intelligence **[3A]**

### 8.1 Rankings

Provide separate views for:

- products by gross sales;
- products by units sold;
- products by distinct orders.

### 8.2 Product share and Pareto

```text
product_revenue_share = product_gross_sales / total_gross_sales
```

Products are ordered by gross sales and given a cumulative share. The module shows:

- the share generated by the top 20% of products;
- how many products are required to reach 80% of gross sales;
- a cumulative Pareto visualization.

### 8.3 Growth, rising and falling products

For each product, compare current and selected baseline periods using gross sales, units and orders.

- Rising/falling rankings default to absolute gross-sales change to avoid tiny baselines dominating the result.
- Percentage change is shown when the baseline is greater than zero.
- Products absent from the baseline are labelled **New**, not assigned infinite growth.
- Products absent from the current period but present in the baseline are labelled **No current sales**.

### 8.4 Dormant products

The user selects an inactivity window of 30, 60 or 90 days; the default is 60 days.

A product is dormant when:

- it has at least one earlier sale; and
- it has no sale within the selected inactivity window ending on the dataset's latest date.

The table includes last-sale date, days inactive, earlier gross sales and earlier order count.

### 8.5 Product price history

Price history uses a quantity-weighted average realized unit price:

```text
weighted_unit_price = SUM(quantity × unit_price) / SUM(quantity)
```

The chart uses the same automatic daily/weekly/monthly granularity rules as the sales trend. The UI describes price movement but does not claim causal price elasticity.

### 8.6 Order penetration

```text
order_penetration = orders_containing_product / all_orders
```

Penetration is calculated within the active reporting range.

### 8.7 Basket affinity

For unordered product pairs:

```text
support(A,B)    = orders_with_A_and_B / all_orders
confidence(A→B) = orders_with_A_and_B / orders_with_A
lift(A→B)       = confidence(A→B) / order_penetration(B)
```

A pair is eligible only when:

- it occurs in at least 10 shared orders; and
- support is at least 0.1%.

Results display shared orders, support, directional confidence and lift. Ranking should emphasize evidence and lift rather than raw popularity alone. Orders excluded by the 100-product safeguard are disclosed.

## 9. Customer Intelligence **[3B]**

All metrics in this section use identified orders only and return the current customer-coverage metadata.

### 9.1 Identified customers

Distinct non-blank customer IDs with activity in the active reporting range.

### 9.2 New versus returning customer revenue

- A customer's first purchase is found using full history.
- Orders on the customer's first purchase date contribute to **new-customer gross sales**.
- Orders on later dates contribute to **returning-customer gross sales**.
- The active reporting range determines which revenue is displayed.

### 9.3 Repeat-purchase rate

Within the population of identified customers active in the reporting range:

```text
repeat_purchase_rate = customers_with_2+_lifetime_orders_by_range_end
                       / identified_customers_active_in_range
```

### 9.4 Time between purchases

Calculate elapsed calendar days between consecutive distinct orders for the same customer. Show median as the primary measure and an interpretable distribution; do not rely on mean alone.

### 9.5 Monthly cohort retention

- Acquisition cohort is the calendar month of first purchase.
- Month 0 is the acquisition month.
- Month N retention is the percentage of the original cohort placing at least one order in calendar month N after acquisition.
- The heatmap shows retention percentage and retained customer count.
- Cohort size and maturity are visible so incomplete right-edge cells are not mistaken for zero retention.

### 9.6 Historical Customer Value

This is an observed measure, not a prediction:

```text
historical_customer_value = cumulative identified gross sales / identified customers
```

The module shows average and median value, along with cumulative value by cohort age. UI wording uses **Historical Customer Value**, not an unsupported lifetime claim.

### 9.7 RFM segmentation

RFM uses all identified activity through the selected end date:

- **Recency:** days since latest order; fewer days receives a higher score.
- **Frequency:** distinct orders; more orders receives a higher score.
- **Monetary:** gross sales; higher sales receives a higher score.

Each dimension receives a dataset-relative quintile score from 1–5. Deterministic tie handling is required. Score combinations map to documented, explainable segments such as Champions, Loyal, Potential Loyalists, Needs Attention, At Risk and Lost.

The UI states that segments are relative to the uploaded customer base and are not universal benchmarks. Drill-down is aggregate only.

### 9.8 Purchase-frequency distribution

Show the distribution of distinct orders per identified customer through the selected end date, including single-order customers and appropriate grouped buckets for the long tail.

### 9.9 Customer concentration

Rank identified customers by gross sales within the reporting range and calculate the share contributed by the top customer decile.

```text
top_decile_share = gross_sales_from_top_10_percent_of_customers
                   / identified_customer_gross_sales
```

No individual identifiers are returned.

## 10. Projected 12-Month Customer Value **[3C]**

### 10.1 Positioning

The predictive metric is named **Projected 12-Month Customer Value**. It is not called infinite-horizon LTV and must not be blended with Historical Customer Value.

### 10.2 Transparent cohort method

For each monthly acquisition cohort:

1. Calculate observed cumulative gross sales per acquired customer by cohort age month.
2. Use eligible mature cohorts to calculate the weighted average incremental value per customer for each remaining age month through month 12.
3. For an immature cohort, retain its observed value and add only the missing age-month increments from mature cohort behavior.
4. Display the observed portion, projected portion, contributing mature-cohort count and data cutoff.

The method does not use BG/NBD, Gamma-Gamma, clustering or a black-box ML model.

### 10.3 Required presentation

- Label every projected value as an estimate.
- Show the fixed 12-month horizon.
- Show eligibility status and contributing data.
- Do not show a value when an eligibility condition fails.
- Do not imply causal, accounting-profit or guaranteed future-revenue meaning.

## 11. Architecture

### 11.1 Technology choices

- **Frontend:** React SPA with Recharts.
- **Backend:** FastAPI JSON REST API.
- **Analytics:** DuckDB SQL.
- **Packaging:** one Docker image; FastAPI serves API and compiled frontend.
- **Runtime:** one application instance with local temporary storage.

Superset and semantic-metrics frameworks are deferred.

### 11.2 Analytics domains

Backend analytics code is organized into:

- `overview`;
- `customers`;
- `products`;
- shared filters, periods, availability and metric definitions.

Metric definitions should have one authoritative implementation and documentation source to prevent formulas drifting across APIs, tests and UI labels.

### 11.3 Hybrid computation

During canonical import, create reusable structures such as:

- `order_lines` — validated canonical line items;
- `order_facts` — one row per order;
- `customer_facts` — stable customer acquisition and lifetime facts when IDs exist;
- `product_facts` — reusable product-level facts.

Stable facts are calculated once. Date-dependent metrics are calculated on request. Identical responses may use a bounded short-lived cache keyed by dataset, module, date range, comparison mode and relevant options.

### 11.4 API shape

The exact paths may evolve, but the domain boundaries are:

| Resource | Purpose |
| --- | --- |
| Dataset availability | Metadata, date range, column capabilities, coverage and eligibility |
| Overview analytics | Existing KPIs, trend and comparison |
| Customer analytics | Retention, cohort, RFM, value and customer diagnostics |
| Product analytics | Portfolio-level product analysis |
| Product detail | One product's trend, price, penetration and related products |

One module endpoint is preferred over one giant dashboard response or one endpoint per metric. Every dataset-specific endpoint requires the existing bearer token.

## 12. Persistence and Lifecycle

- Each upload continues to use one per-dataset DuckDB file.
- Canonical and derived tables live in that same file.
- The raw CSV is deleted after successful import.
- The dataset ID remains a locator; the separate bearer token remains the credential.
- Dataset, cache entries and token expire together after 24 hours.
- Cleanup deletes the complete dataset file and associated cache entries.
- No central application database is introduced in Phase 3.

A central database for users, ownership, durable datasets and saved dashboards is a Phase 4 candidate.

## 13. Deployment and Demo

### 13.1 Deployment model

- Keep the single self-contained Docker image.
- Self-hosted deployments retain full CSV upload behavior.
- Public-demo mode remains sample-only and rejects uploads at the server.
- No background workers, shared storage or horizontal scaling are introduced.

### 13.2 Synthetic demo dataset

Expand the deterministic dataset so every Phase 3 feature can be shown:

- 24 months of history;
- approximately 10,000 orders;
- at least 500 identified customers, preferably 1,500–2,000;
- 25–50 products;
- at least 80% customer coverage;
- repeat-purchase behavior and distinct acquisition cohorts;
- uneven product popularity and a long tail;
- seasonality, rising/falling products and dormant products;
- known basket-affinity patterns;
- price variation;
- fixed seed and expected golden results;
- synthetic opaque customer IDs only.

Separate small fixtures demonstrate low coverage, missing IDs, immature cohorts and validation failures.

## 14. Security and Privacy

All existing protections remain, including upload limits, server-generated paths, token hashing, parameterized filters, restrictive CORS, private temporary files and privacy-safe logs.

Phase 3 adds these controls:

- best-effort PII-pattern validation for `customer_id`;
- no customer identifiers in analytics API responses;
- no customer-level search, list, download or export;
- no logging of customer IDs, cohort membership or RFM records;
- capability/coverage metadata contains counts only;
- caches inherit dataset authorization and expiry boundaries.

The product must not claim that opaque or hashed IDs are anonymous. They are temporary pseudonymous data and remain subject to the 24-hour lifecycle.

## 15. Performance Targets **[3C]**

On documented reference hardware:

| Operation | Target |
| --- | --- |
| Validate and import 500,000 rows | 30 seconds or less |
| Uncached module response | 3 seconds or less |
| Cached module response | 1 second or less |

These are repeatable engineering budgets, not guarantees for every machine. Benchmark data, hardware, commands and results must be documented.

## 16. Testing and Quality Bar

### 16.1 Formula tests

Every metric requires deterministic tests for its numerator, denominator, date boundaries, empty state, zero baseline and comparison behavior.

### 16.2 Golden datasets

Use small, human-verifiable deterministic datasets with exact expected results for:

- product share and Pareto;
- growth classifications;
- dormancy;
- price history;
- penetration and basket support/confidence/lift;
- customer coverage and first-purchase identity;
- repeat purchase and reorder intervals;
- cohorts and mature/incomplete cells;
- historical customer value;
- RFM scoring and segments;
- purchase frequency and concentration;
- projection eligibility and cohort projection.

### 16.3 Integration tests

Cover:

- import and creation of derived facts;
- optional/missing/conflicting customer IDs;
- PII guardrails;
- module API authorization;
- global dates and comparison modes;
- coverage and eligibility states;
- exclusion of extreme orders from basket analysis;
- cache correctness, isolation and expiry;
- cleanup of canonical and derived data.

### 16.4 Browser test

One stable browser happy path should:

1. load the Phase 3 sample dataset;
2. verify Overview comparison behavior;
3. visit Products and exercise a product analysis;
4. visit Customers and verify coverage, cohort and RFM content;
5. verify projected value and its explanatory metadata;
6. change the global range and confirm consistent updates across modules.

### 16.5 Release-quality definition of done

A backlog item is complete only when all applicable parts exist:

- production implementation;
- formula/unit tests;
- integration coverage;
- API schema and documentation;
- loading, empty, error, warning and insufficient-data UI states;
- sample/golden data updates;
- security review against this specification;
- relevant benchmark evidence;
- user-facing documentation.

Feature code alone is not complete.

## 17. Phase 3 Boundaries

### 17.1 Included

- Overview, Customers and Products sections
- Previous-period and optional YoY comparison
- Optional `customer_id` with privacy and consistency validation
- Tiered customer-coverage behavior
- Product ranking, share, Pareto, growth, dormancy, price, penetration and affinity
- Customer retention, cohorts, historical value, RFM, frequency and concentration
- Transparent 12-month cohort projection with strict eligibility
- Derived DuckDB fact structures and bounded response cache
- Expanded deterministic demo and golden fixtures
- Performance benchmarks
- Release-quality tests and documentation

### 17.2 Explicit Phase 3 non-goals

- accounts, multi-tenancy and permanent saved dashboards;
- public CSV uploads or a managed hosted service;
- discounts, refunds, costs, margin or accounting net sales;
- Shopify, WooCommerce, Trendyol, Hepsiburada or other connectors/mappers;
- multiple files, incremental imports or dataset merging;
- customer lists, customer exports or marketing activation;
- raw personal data;
- mixed currencies or currency conversion;
- sales forecasting, anomaly detection or AI-generated insights;
- custom dashboards, arbitrary metrics, SQL editing or general BI behavior;
- Superset migration or embedding;
- predictive models beyond the transparent 12-month cohort projection;
- background-job infrastructure, distributed deployment or horizontal scaling.

## 18. Prioritized Delivery Backlog

### 18.1 Phase 3A — Product Intelligence

#### P0 — Analytics foundation

- **3A-01:** Add stable reporting/comparison-period utilities with previous-period and YoY modes.
- **3A-02:** Introduce authoritative shared metric definitions and SQL/domain module boundaries.
- **3A-03:** Create `order_facts` and `product_facts` during import.
- **3A-04:** Add dataset capability/availability metadata.
- **3A-05:** Add module-level Overview and Product APIs with typed responses.
- **3A-06:** Add bounded cache keys and invalidation tied to dataset expiry.

#### P0 — Product analytics

- **3A-07:** Implement revenue, unit and order rankings.
- **3A-08:** Implement product share and Pareto analysis.
- **3A-09:** Implement product comparison, rising/falling classification and zero-baseline behavior.
- **3A-10:** Implement 30/60/90-day dormancy with a 60-day default.
- **3A-11:** Implement weighted price history.
- **3A-12:** Implement order penetration.
- **3A-13:** Implement basket support, confidence and lift with evidence thresholds.
- **3A-14:** Exclude and report orders with more than 100 distinct products from basket analysis.

#### P0 — Product UI and quality

- **3A-15:** Add Overview/Customers/Products navigation; Customers may initially show a planned-capability state.
- **3A-16:** Build Product portfolio and product-detail views.
- **3A-17:** Add exact current/comparison date labels and unavailable YoY states.
- **3A-18:** Add formula, golden, API and UI tests for 3A.
- **3A-19:** Document all Product formulas and caveats.

### 18.2 Phase 3B — Customer Intelligence

#### P0 — Contract and facts

- **3B-01:** Add optional nullable `customer_id` to the documented contract.
- **3B-02:** Implement fill-blank/reject-conflict order consistency.
- **3B-03:** Implement bounded opaque-ID and best-effort email/phone validation.
- **3B-04:** Calculate order-level coverage and tiered feature availability.
- **3B-05:** Create stable `customer_facts` using full prior history.
- **3B-06:** Add Customer module API with aggregate-only responses.

#### P0 — Customer analytics

- **3B-07:** Implement identified-customer count.
- **3B-08:** Implement new versus returning customer gross sales.
- **3B-09:** Implement repeat-purchase rate.
- **3B-10:** Implement median/distribution of days between purchases.
- **3B-11:** Implement monthly acquisition-cohort retention with maturity states.
- **3B-12:** Implement Historical Customer Value by customer and cohort age.
- **3B-13:** Implement deterministic dataset-relative RFM quintiles and named segments.
- **3B-14:** Implement aggregate RFM segment drill-downs.
- **3B-15:** Implement purchase-frequency distribution.
- **3B-16:** Implement top-decile customer concentration without returning identifiers.

#### P0 — Customer UI and quality

- **3B-17:** Build Customer coverage and availability states.
- **3B-18:** Build retention, cohort, value, RFM, frequency and concentration views.
- **3B-19:** Add low-coverage and suppressed-module explanations.
- **3B-20:** Expand synthetic data and privacy/coverage/golden fixtures.
- **3B-21:** Add formula, golden, API, authorization and browser coverage for 3B.
- **3B-22:** Document customer semantics, privacy limitations and coverage bias.

### 18.3 Phase 3C — Predictive & Polish

#### P0 — Projection

- **3C-01:** Implement projection eligibility evaluation and explanations.
- **3C-02:** Implement mature-cohort incremental 12-month projection.
- **3C-03:** Separate observed and projected components in API responses.
- **3C-04:** Build projection presentation with horizon, cutoff and contributing-cohort metadata.
- **3C-05:** Add golden tests for eligible, ineligible and partially mature cohort cases.

#### P0 — Performance and delivery

- **3C-06:** Create reproducible 500,000-row and module-query benchmarks.
- **3C-07:** Tune facts, SQL and caches to the agreed performance budgets.
- **3C-08:** Verify cache authorization, isolation, expiry and cleanup.
- **3C-09:** Complete the cross-module browser happy path.
- **3C-10:** Complete accessibility, responsive layout and all empty/error/warning states.
- **3C-11:** Update architecture, metric catalogue, privacy, benchmark and self-hosting documentation.
- **3C-12:** Publish a final Phase 3 release checklist and evidence report.

## 19. Release Acceptance Criteria

### 19.1 Phase 3A is complete when

1. Existing six-column files work without modification.
2. Overview comparisons use exact, visible current and baseline periods.
3. Every agreed Product analysis follows its documented formula.
4. Basket results enforce evidence and extreme-order safeguards.
5. Product APIs and UI meet security, test and relevant performance requirements.

### 19.2 Phase 3B is complete when

1. Files with and without `customer_id` both behave correctly.
2. Missing and conflicting IDs follow the agreed order-level rules.
3. Coverage controls Customer-module availability exactly as specified.
4. Full-history identity prevents customers being incorrectly reclassified as new.
5. Cohort, historical value, RFM, frequency and concentration results match golden datasets.
6. No customer identifier is returned to the browser.

### 19.3 Phase 3C is complete when

1. The projection is shown only for eligible datasets.
2. Its observed and projected portions are explainable and reproducible.
3. The 24-month public sample demonstrates all Phase 3 modules.
4. Benchmarks meet the agreed budgets on documented reference hardware.
5. All release-quality definition-of-done requirements are satisfied.

## 20. Deferred Roadmap

### Phase 4 candidates already preserved

1. **Managed product foundation:** central application database, accounts, ownership, saved datasets and persistent dashboards.
2. **Hosted ingestion:** protected public uploads with rate limits, isolation, abuse controls and monitoring.
3. **Financial contract layer:** optional `discount_amount`, `refund_amount`, and `unit_cost` with net sales, discount, refund and margin analytics.

### Later candidates

- Shopify, WooCommerce and marketplace format mappers;
- multi-file and multi-channel dataset merging;
- customer activation/export workflows with an explicit privacy model;
- larger asynchronous imports;
- advanced forecasting or anomaly detection only after a validated user need;
- Superset or a semantic layer only when maintaining custom analytics becomes a demonstrated constraint.

## 21. Decision Record

| Area | Agreed decision |
| --- | --- |
| Phase objective | Portfolio-quality analytics engine |
| Primary story | Customer retention and value |
| Secondary story | Product performance and merchandising |
| Target product shape | Generic e-commerce CSV analytics |
| Dashboard | Overview, Customers, Products |
| Required schema | Existing six columns unchanged |
| Optional schema | `customer_id` only |
| Missing customer IDs | Allowed; coverage is disclosed |
| Customer conflict | Fill unambiguous blanks; reject conflicting IDs per order |
| Customer privacy | Opaque IDs, best-effort PII validation, aggregate responses only |
| Customer coverage | Suppress below 50%; warn at 50–79%; normal at 80%+ |
| Customer history | Full prior history defines identity and cohorts |
| Customer scope | Full suite: retention, cohorts, value, RFM, frequency, concentration |
| Historical value | Observed Historical Customer Value |
| Predictive value | Transparent Projected 12-Month Customer Value |
| Projection eligibility | 18 months, 500 customers, 70% coverage, five mature cohorts |
| Product scope | Focused merchandising suite |
| Comparisons | Previous equal period plus optional YoY |
| Dormancy | 30/60/90-day selector; 60-day default |
| Basket evidence | 10 shared orders and 0.1% support minimum |
| Basket safeguard | Exclude orders with more than 100 products from affinity only |
| Cohorts | Monthly acquisition cohorts |
| RFM | Dataset-relative quintiles and named segments |
| Architecture | React, FastAPI, DuckDB; domain query modules and shared definitions |
| Computation | Derived facts plus on-demand filtered metrics and bounded cache |
| Persistence | One 24-hour DuckDB file per dataset |
| API | Module-level resources with existing bearer authorization |
| Deployment | Single Docker image; sample-only public demo |
| Sample data | Deterministic 24-month enriched e-commerce data |
| Performance | 30-second import; 3-second cold; 1-second cached targets |
| Testing | Formula tests, golden data, integration tests and cross-module browser path |
| Delivery | 3A Product, 3B Customer, 3C Predictive & Polish |
| Definition of done | Implementation, tests, docs, UI states, sample data and benchmarks |

