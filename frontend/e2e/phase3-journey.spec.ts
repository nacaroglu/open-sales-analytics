import { expect, test } from "@playwright/test";
import { SAMPLE_CUSTOMERS, SAMPLE_KPIS, keyFigures, openSample } from "./helpers";

test("the Phase 3 browser journey stays coherent across all modules", async ({ page }) => {
  await openSample(page);

  // Overview: the sample opens with the documented full dataset figures.
  await expect(keyFigures(page).grossSales).toHaveText(SAMPLE_KPIS.grossSales);
  await expect(page.getByRole("heading", { level: 2, name: "Overview" })).toBeVisible();

  // Comparison: use the complete 2025 year so the same-period-last-year
  // comparison is available and its dates are explicit in the UI.
  await page.getByLabel("Start date").fill("2025-01-01");
  await page.getByLabel("End date").fill("2025-12-31");
  await page.getByLabel("Compare with").selectOption("previous_year");
  await expect(
    page
      .getByRole("region", { name: "Date range" })
      .getByText("2025-01-01 to 2025-12-31 compared with 2024-01-01 to 2024-12-31 (same period last year)"),
  ).toBeVisible();
  await expect(page.getByRole("region", { name: "Key figures" }).getByText(/vs/).first()).toBeVisible();

  // Products: rankings, the leading product, price history and penetration.
  const productsLink = page.getByRole("link", { name: "Products" });
  await productsLink.click();
  await expect(page).toHaveURL(/\/d\/[^/]+\/products$/);
  const rankings = page.getByRole("region", { name: "Rankings" });
  await expect(rankings).toBeVisible();
  const leadingProduct = rankings.getByRole("row").nth(1).getByRole("link");
  const leadingProductName = await leadingProduct.innerText();
  await expect(leadingProduct).toBeVisible();
  await leadingProduct.click();
  await expect(page.getByRole("heading", { level: 2, name: leadingProductName })).toBeVisible();
  await expect(page.getByRole("img", { name: /Weighted unit price/ })).toBeVisible();
  await expect(page.getByRole("region", { name: "Order penetration" })).toContainText(/of orders/);
  await page.getByRole("link", { name: "All products" }).click();

  // Customers: coverage, cohort retention, RFM and the projection all render
  // from the same response and retain the sample's golden coverage values.
  await page.getByRole("link", { name: "Customers" }).click();
  await expect(page).toHaveURL(/\/d\/[^/]+\/customers$/);
  const coverage = page.getByRole("region", { name: "Customer coverage" });
  await expect(coverage).toContainText(SAMPLE_CUSTOMERS.coverage);
  await expect(coverage).toContainText(SAMPLE_CUSTOMERS.identifiedOrders);
  await expect(coverage).toContainText(SAMPLE_CUSTOMERS.unidentifiedOrders);

  const cohort = page.getByRole("region", { name: "Cohort retention" });
  await expect(cohort.getByRole("table", { name: "Cohort retention table" })).toBeVisible();
  await expect(cohort.getByRole("row").nth(1)).toContainText(/\d+\.\d+% \(\d+\)/);

  const rfm = page.getByRole("region", { name: "RFM segments" });
  await expect(rfm.getByRole("table", { name: "RFM segments table" })).toBeVisible();
  await expect(rfm.getByRole("row").nth(1)).toContainText(/\d+%/);
  await rfm.getByRole("row").nth(1).getByRole("button").click();
  await expect(page.getByRole("region", { name: "RFM segment drill-down" })).toBeVisible();

  const projection = page.getByRole("region", { name: "Projected 12-Month Customer Value" });
  await expect(projection).toContainText("Estimate");
  await expect(projection).toContainText("12-month horizon");
  await expect(projection).toContainText(/Data up to \d{4}-\d{2}-\d{2}/);
  await expect(projection).toContainText(/based on \d+ mature cohorts? · \d+ customers/);
  await expect(projection.getByRole("table", { name: "Projected 12-Month Customer Value table" })).toBeVisible();
  await expect(projection.getByRole("columnheader", { name: "Observed" })).toBeVisible();
  await expect(projection.getByRole("columnheader", { name: "Projected (estimate)" })).toBeVisible();

  // A shared range survives navigation between the three modules.
  await page.getByRole("link", { name: "Overview" }).click();
  await expect(page.getByLabel("Start date")).toHaveValue("2025-01-01");
  await expect(page.getByLabel("End date")).toHaveValue("2025-12-31");
  await expect(page.getByRole("heading", { level: 2, name: "Overview" })).toBeVisible();
  await page.getByRole("link", { name: "Products" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Products" })).toBeVisible();
  await page.getByRole("link", { name: "Customers" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Customers" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Customer coverage" })).toContainText(SAMPLE_CUSTOMERS.coverage);
});
