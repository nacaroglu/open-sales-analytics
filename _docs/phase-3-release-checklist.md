# Phase 3 release checklist and evidence report

Release commit: **pending merge**  
Checklist branch: [`feature/issue-141`](https://github.com/nacaroglu/open-sales-analytics/tree/feature/issue-141)  
Evidence date: 2026-10-20  
Release owner: Open Sales Analytics maintainers

This is the release gate for Phase 3. Evidence links point to the commits that
introduced or verified each capability. The final release SHA and green `main`
workflow run must be filled in after this branch is merged; that gate is listed
as an explicit gap rather than being inferred from a pull-request run.

## Gate summary

| Gate | Status | Evidence |
| --- | --- | --- |
| Phase 3A criteria (§19.1) | Met | Criteria 1–5 below |
| Phase 3B criteria (§19.2) | Met | Criteria 6–11 below |
| Phase 3C criteria (§19.3) | Met, release gate pending | Criteria 12–16 below |
| Final release SHA and green `main` CI | Gap | [Issue #141](https://github.com/nacaroglu/open-sales-analytics/issues/141) — rerun all required checks on the merged release SHA |

## §19.1 — Phase 3A completion

| # | Criterion | Status | Evidence |
| ---: | --- | --- | --- |
| 1 | Six-column files remain valid; `customer_id` is the only optional field | Met | [`test_validation_structure.py`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_validation_structure.py), [`test_sample_dataset.py`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_sample_dataset.py) |
| 2 | Overview comparisons show exact current and baseline periods | Met | [`dashboard.spec.ts` comparison coverage](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/frontend/e2e/dashboard.spec.ts), [`phase3-journey.spec.ts` lines 11–17](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/frontend/e2e/phase3-journey.spec.ts#L11-L17) |
| 3 | Product analyses document formulas and caveats | Met | [`metrics.md`](metrics.md), [`test_metric_docs.py`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_metric_docs.py) |
| 4 | Basket analysis has safeguards and explicit unavailable states | Met | [`test_product_basket.py`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_product_basket.py), [`test_basket.spec.ts`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/frontend/e2e/products.spec.ts) |
| 5 | Product APIs/UI meet security, test and performance expectations | Met | [`test_product_rankings.py`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_product_rankings.py), [`test_cache_security.py`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_cache_security.py), [after-tuning benchmark](benchmarks.md#after-tuning--stability-check-136) |

## §19.2 — Phase 3B completion

| # | Criterion | Status | Evidence |
| ---: | --- | --- | --- |
| 6 | Customer analytics works with and without `customer_id` | Met | [`test_customer_coverage.py`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_customer_coverage.py), [`test_customers_endpoint.py`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_customers_endpoint.py) |
| 7 | Missing/conflicting IDs are resolved at order level | Met | [`test_importer.py` blank-ID fill](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_importer.py), [`test_customers_endpoint.py` filled lines in customer sales](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_customers_endpoint.py), [`test_customer_fixtures.py`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_customer_fixtures.py), [`test_validation_cross_row.py`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_validation_cross_row.py) |
| 8 | Coverage controls module availability | Met | [`test_customer_coverage.py`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_customer_coverage.py), [`customers.spec.ts`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/frontend/e2e/customers.spec.ts) |
| 9 | Full-history identity supports new/returning classification | Met | [`test_customer_new_vs_returning.py`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_customer_new_vs_returning.py), [`test_customer_identified.py`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_customer_identified.py) |
| 10 | Cohort, historical value, RFM, frequency and concentration results have golden coverage | Met | [`test_customer_golden.py`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_customer_golden.py), [`test_customer_rfm.py`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_customer_rfm.py), [`test_customer_historical_value.py`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_customer_historical_value.py) |
| 11 | No customer identifier is returned to the browser | Met | [`test_customers_endpoint.py`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_customers_endpoint.py), [`test_customer_rfm_drilldown.py`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_customer_rfm_drilldown.py), [`phase3-journey.spec.ts` lines 34–60](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/frontend/e2e/phase3-journey.spec.ts#L34-L60) |

## §19.3 — Phase 3C completion

| # | Criterion | Status | Evidence |
| ---: | --- | --- | --- |
| 12 | Projection is offered only when eligibility conditions are met | Met | [`test_projection_eligibility.py`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_projection_eligibility.py), [`test_projection_endpoint.py`](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_projection_endpoint.py) |
| 13 | Observed and projected values are explainable and reproducible | Met | [`test_projection_golden.py` eligible and reproducibility tests](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_projection_golden.py#L182-L245), [`phase3-journey.spec.ts` lines 53–60](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/frontend/e2e/phase3-journey.spec.ts#L53-L60) |
| 14 | The public 24-month sample demonstrates all Phase 3 modules | Met | [cross-module journey](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/frontend/e2e/phase3-journey.spec.ts), [sample projection contract](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_projection_golden.py#L328-L336), [Overview screenshot](images/phase-3/overview.png), [Products screenshot](images/phase-3/products.png), [Product detail screenshot](images/phase-3/product-detail.png), [Customers screenshot](images/phase-3/customers.png), [Projection screenshot](images/phase-3/projection.png) |
| 15 | Benchmarks document the reference hardware, numbers and budgets | Met | [benchmark environment and results](benchmarks.md#baseline-environment-and-input), [after-tuning results](benchmarks.md#after-tuning--stability-check-136) |
| 16 | All release-quality requirements are evidenced below | Met, release gate pending | §16.5 evidence matrix below; final merged SHA/main CI remains the only open release gate |

### §16.5 release-quality evidence matrix

| Part | Status | Evidence |
| --- | --- | --- |
| Production implementation | Met | [architecture guide](architecture.md), [metric catalogue](metrics.md), [Phase 3 specification](open_sales_analytics_phase_3_spec.md) |
| Formula and unit tests | Met | [metric tests](https://github.com/nacaroglu/open-sales-analytics/tree/feature/issue-141/backend/tests), [documentation metric-key test](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_metric_docs.py) |
| Integration coverage | Met | [API tests](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_module_endpoints.py), [browser journey](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/frontend/e2e/phase3-journey.spec.ts) |
| API schema and docs | Met | [OpenAPI/schema tests](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_schema.py), [architecture endpoint map](architecture.md#http-api-surface) |
| Loading, empty, error, warning and insufficient-data UI states | Met | [responsive/UI-state journey](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/frontend/e2e/responsive.spec.ts), [customer state tests](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/frontend/e2e/customers.spec.ts), [design-system state guidance](design-system.md) |
| Sample/golden data | Met | [sample dataset test](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_sample_dataset.py), [customer goldens](https://github.com/nacaroglu/open-sales-analytics/tree/feature/issue-141/backend/tests/fixtures/customers), [projection goldens](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_projection_golden.py) |
| Security review | Met | [cache authorization/isolation tests](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_cache_security.py), [customer privacy tests](https://github.com/nacaroglu/open-sales-analytics/blob/feature/issue-141/backend/tests/test_customer_rfm_drilldown.py), [privacy contract](../README.md#privacy) |
| Benchmark evidence | Met | [benchmark report](benchmarks.md) — After numbers use the reference WSL2 machine, Python 3.12.7, DuckDB 1.5.6 and four logical CPUs; every listed budget is `yes` |
| User-facing documentation | Met | [README](../README.md), [architecture guide](architecture.md), [metric catalogue](metrics.md) |

## Required CI and release gate

The repository workflow defines these required checks: Backend (tests,
ruff, mypy), Frontend (tests, lint, type check, build), pinned actions,
dependency scan, and Container (build, smoke, browser tests). The workflow is
defined in [`ci.yml`](../.github/workflows/ci.yml).

| Required evidence | Status | Link |
| --- | --- | --- |
| Green checks on the final release SHA pushed to `main` | Gap | [Issue #141](https://github.com/nacaroglu/open-sales-analytics/issues/141) — fill this row after merge with the run URL and SHA |
| Pull-request evidence for this checklist | Pending | [PR search for `feature/issue-141`](https://github.com/nacaroglu/open-sales-analytics/pulls?q=is%3Apr+head%3Afeature%2Fissue-141) |

No gap is silently accepted: the only current gap is the post-merge release
verification, and it links back to open Phase 3C issue #141.

## Phase 3 issue disposition

Issues #89–#133 are closed. Issues #134–#141 are the open Phase 3C work items;
each is linked below so an unresolved item has an explicit owner and follow-up.

| Issues | Disposition |
| --- | --- |
| [#89–#133](https://github.com/nacaroglu/open-sales-analytics/issues?q=is%3Aissue+is%3Aclosed+milestone%3A%22Phase+3%22) | Closed |
| [#134](https://github.com/nacaroglu/open-sales-analytics/issues/134) | Open — golden projection tests; PR [#204](https://github.com/nacaroglu/open-sales-analytics/pull/204) |
| [#135](https://github.com/nacaroglu/open-sales-analytics/issues/135) | Open — reproducible benchmark; PR [#205](https://github.com/nacaroglu/open-sales-analytics/pull/205) |
| [#136](https://github.com/nacaroglu/open-sales-analytics/issues/136) | Open — tuning verification; PR [#206](https://github.com/nacaroglu/open-sales-analytics/pull/206) |
| [#137](https://github.com/nacaroglu/open-sales-analytics/issues/137) | Open — cache security verification; PR [#207](https://github.com/nacaroglu/open-sales-analytics/pull/207) |
| [#138](https://github.com/nacaroglu/open-sales-analytics/issues/138) | Open — browser journey; PR [#208](https://github.com/nacaroglu/open-sales-analytics/pull/208) |
| [#139](https://github.com/nacaroglu/open-sales-analytics/issues/139) | Open — accessibility and responsive UI; PR [#209](https://github.com/nacaroglu/open-sales-analytics/pull/209) |
| [#140](https://github.com/nacaroglu/open-sales-analytics/issues/140) | Open — architecture and metric documentation; PR [#210](https://github.com/nacaroglu/open-sales-analytics/pull/210) |
| [#141](https://github.com/nacaroglu/open-sales-analytics/issues/141) | Open — this checklist; release SHA/main CI gate |

## Verification notes

- The five release screenshots were captured from the committed 24-month sample
  in an isolated worktree, so they do not include the separate local change to
  `backend/app/sample/sample_sales.csv`.
- No customer identifier appears in the screenshots or browser response
  assertions; customer views use aggregate labels and counts only.
- The release SHA and `main` CI run are intentionally not fabricated before
  merge. Once the PR is merged, replace the two `Gap/Pending` links above with
  the immutable commit and Actions run URLs, then close #141.
