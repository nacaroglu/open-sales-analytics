# Open Sales Analytics — Phase 2 Plan

## Phase Goal

Turn the locally working MVP into a reliable, reproducible, and portfolio-ready open-source project without expanding it into a general-purpose BI platform.

Phase 2 focuses on:

- UX correctness and clarity
- Automated verification
- Security and lifecycle behavior
- Reproducible packaging
- Continuous integration
- A safe public demo
- High-quality project presentation

## Scope Guardrails

The following features remain out of scope for Phase 2:

- User accounts and permanent workspaces
- Durable upload history
- Multiple datasets per user
- Shopify, WooCommerce, or Stripe integrations
- Returns and cancellation analysis
- Period-over-period comparison
- PDF or aggregate CSV exports
- Background jobs and distributed processing
- AI-generated analysis
- General-purpose dashboard or query builders

---

## 1. Resolve Visible UX and Formatting Issues

### Work

- Use consistent English formatting for application-generated dates.
- Show dataset expiry primarily as relative time, such as `Expires in 23 hours`.
- Optionally show the exact expiry timestamp as secondary text or in a tooltip.
- Add helper text when the Upload button is disabled:
  `Select a CSV file and currency to continue.`
- Confirm that loading, empty, disabled, success, warning, and error states are visually distinct.
- Keep browser-native file picker localization as-is; it is controlled by the user's browser.

### Acceptance Criteria

- Application-generated dates do not mix English and Turkish locale formats.
- Users can understand why Upload is unavailable.
- All major interaction states have clear feedback.

---

## 2. Make Partial Time Buckets Explicit

### Work

- Detect incomplete daily, weekly, and monthly buckets at dataset boundaries.
- Mark incomplete buckets as `Partial period` in chart tooltips.
- Prefer date-range labels such as `Dec 29–31` instead of only `Week of Dec 29` when a bucket is incomplete.
- Ensure the first and last buckets cannot be mistaken for complete periods.
- Document the bucketing rules in the README or API documentation.

### Acceptance Criteria

- A short first or last week is visibly identified as partial.
- Users are not led to interpret a partial bucket as a sudden sales decline.
- Bucket boundaries are covered by automated tests.

---

## 3. Complete Backend Unit Tests

### Work

- Test the six required CSV fields:
  `order_id`, `order_date`, `product_id`, `product_name`, `quantity`, and `unit_price`.
- Test required-value, type, date, future-date, quantity, price, uniqueness, and product-name consistency rules.
- Test warnings for zero prices and ignored extra columns.
- Test all-or-nothing file rejection.
- Test the 50 MB and 500,000-row limits where practical, using focused boundary tests rather than unnecessarily large fixtures.
- Test daily, weekly, and monthly aggregation logic.
- Test gross sales, order count, units sold, average order value, and top-product calculations.

### Acceptance Criteria

- Core validation and metric calculations are deterministic and covered by pytest.
- Every validation error and warning code has at least one test.
- Test failures clearly identify the broken business rule.

---

## 4. Add API and Dataset Lifecycle Integration Tests

### Work

- Test successful upload, validation, DuckDB creation, and initial summary response.
- Confirm that the raw CSV is deleted after successful import.
- Confirm that an invalid upload does not leave a usable dataset behind.
- Verify dataset ID and bearer-token enforcement.
- Verify invalid, missing, and expired tokens.
- Verify dataset expiry and 24-hour cleanup behavior.
- Verify consistent date filtering across KPI, trend, and top-product endpoints.

### Acceptance Criteria

- The complete upload-to-dashboard API flow runs without a browser.
- Unauthorized or expired access cannot retrieve dataset data.
- Temporary files are cleaned up according to the specification.

---

## 5. Complete Frontend Component Tests

### Work

- Test file and currency selection behavior.
- Test disabled and enabled Upload states.
- Test validation-error and warning rendering.
- Test KPI cards with formatted values and currency.
- Test date-range selection and Reset behavior.
- Test loading, empty, API-error, and expired-dataset states.
- Test trend and top-product components with deterministic fixtures.
- Verify accessible labels for form controls, buttons, charts, and error messages.

### Acceptance Criteria

- Critical React behavior is covered with Vitest and React Testing Library.
- Tests assert user-visible behavior rather than implementation details.
- The dashboard remains usable with keyboard navigation and screen-reader labels.

---

## 6. Add Playwright End-to-End Tests

### Work

Implement a small, stable browser suite covering:

1. Load deterministic sample data and open the dashboard.
2. Upload a valid CSV and verify KPIs and charts.
3. Upload an invalid CSV and verify actionable rejection details.
4. Apply and reset a date-range filter.
5. Start another analysis from the dashboard.
6. Verify the expired-dataset experience using controlled test configuration.

### Acceptance Criteria

- The primary `Upload → Validate → Explore dashboard` journey passes automatically.
- Tests use stable selectors and deterministic data.
- Browser tests can run locally and in CI without manual steps.

---

## 7. Finalize the Single-Container Distribution

### Work

- Build the React application and serve the SPA and FastAPI API from the same origin.
- Use a multi-stage Docker build.
- Run the final container as a non-root user.
- Persist temporary DuckDB files only in the intended application data directory.
- Add a health endpoint and container health check.
- Set explicit upload, timeout, and storage configuration defaults.
- Add `.dockerignore` and exclude development artifacts and secrets.
- Verify startup and shutdown behavior, including cleanup scheduling.

### Acceptance Criteria

- A new user can run the complete application with one documented Docker command.
- No Node.js build toolchain is present in the final runtime image unless required.
- The runtime process is non-root and the health check reports correctly.

---

## 8. Establish GitHub Actions CI and Quality Gates

### Work

- Run backend formatting/linting with Ruff.
- Run Python type checks with mypy.
- Run backend unit and integration tests with pytest.
- Run frontend type checking, linting, and Vitest.
- Build the frontend production bundle.
- Build the Docker image.
- Run the Playwright smoke suite against the built application.
- Add dependency and security scanning appropriate to the Zoomcamp module.
- Cache dependencies without caching generated application data.

### Acceptance Criteria

- Every pull request executes the same essential checks used locally.
- A failing quality gate prevents a green CI result.
- The default branch remains buildable and testable from a clean checkout.

---

## 9. Publish a Safe Sample-Only Demo

### Work

- Deploy a public demo that uses deterministic sample data only.
- Disable arbitrary CSV uploads in the hosted demo.
- Clearly state that the hosted demo does not accept user data.
- Keep full CSV upload available in the self-hosted Docker version.
- Verify that no secret, local path, test token, or private dataset is included in the deployment.
- Add a visible link from the demo to self-hosting instructions.

### Acceptance Criteria

- Visitors can explore the complete dashboard without uploading data.
- The public deployment cannot receive arbitrary customer CSV files.
- The difference between hosted-demo and self-hosted capabilities is explicit.

---

## 10. Finish Portfolio and Open-Source Presentation

### Work

- Rewrite the README around the user problem, product boundary, architecture, and quick start.
- Add three or four final screenshots:
  - Upload and data-contract screen
  - KPI and sales-trend dashboard
  - Top-products chart and table
  - Validation-error report, if visually useful
- Record an approximately 90-second demo showing the core journey.
- Add a compact architecture diagram.
- Document the CSV contract, metric definitions, security model, expiry behavior, and known limitations.
- Add `CONTRIBUTING.md`, license information, and issue templates.
- Document how AI coding tools were used for specification, implementation, verification, and review.
- Add a short roadmap that clearly separates completed MVP work from post-MVP candidates.

### Acceptance Criteria

- A reviewer can understand, run, and evaluate the project from the README alone.
- The repository demonstrates disciplined AI-assisted engineering, not merely generated code.
- Screenshots, demo, documentation, tests, and deployment reflect the same final behavior.

---

## Recommended Execution Order

Execute the work in the numbered order above. Items 1–2 stabilize visible behavior; items 3–6 establish correctness; items 7–9 make the application reproducible and safely demonstrable; item 10 packages the result as a strong Zoomcamp and portfolio project.

## Phase 2 Definition of Done

Phase 2 is complete when:

- All ten plan items meet their acceptance criteria.
- Local and CI test suites pass from a clean checkout.
- The application runs through one documented Docker command.
- The hosted demo accepts sample data only.
- README, screenshots, demo video, and architecture documentation are current.
- No post-MVP product feature has been added prematurely.

After this gate, the recommended first Phase 3 feature is period-over-period comparison.
