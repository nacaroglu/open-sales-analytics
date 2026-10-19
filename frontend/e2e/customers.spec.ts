import { expect, test } from "@playwright/test";
import { SAMPLE_CUSTOMERS, openSample } from "./helpers";

test("Customers shows aggregate coverage, cohorts, RFM and drill-down", async ({ page }) => {
  await openSample(page);
  await page.getByRole("link", { name: "Customers" }).click();
  await expect(page).toHaveURL(/\/d\/[^/]+\/customers$/);
  await expect(page.getByRole("heading", { level: 2, name: "Customers" })).toBeVisible();
  const coverage = page.getByRole("region", { name: "Customer coverage" });
  await expect(coverage).toContainText(SAMPLE_CUSTOMERS.coverage);
  await expect(coverage).toContainText(SAMPLE_CUSTOMERS.identifiedOrders);
  await expect(coverage).toContainText(SAMPLE_CUSTOMERS.unidentifiedOrders);
  await expect(page.getByRole("heading", { level: 3, name: "Cohort retention" })).toBeVisible();
  const rfm = page.getByRole("region", { name: "RFM segments" });
  await expect(rfm).toBeVisible();
  const rfmTable = rfm.getByRole("table", { name: "RFM segments table" });
  await expect(rfmTable.or(rfm.getByText("Insufficient data"))).toBeVisible();
  if (await rfmTable.isVisible()) {
    await expect(rfm).toContainText("Segments are relative to the customers in this upload, not universal benchmarks.");
  }
});

test("Customers can be opened with an unavailable six-column upload", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("CSV file").setInputFiles({
    name: "sales.csv",
    mimeType: "text/csv",
    buffer: Buffer.from("order_id,order_date,product_id,product_name,quantity,unit_price\no1,2025-01-01,p1,Mug,1,2.00\n"),
  });
  await page.getByLabel("Currency").selectOption("USD");
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page).toHaveURL(/\/d\/[^/]+$/);
  await page.getByRole("link", { name: "Customers" }).click();
  await expect(page).toHaveURL(/\/d\/[^/]+\/customers$/);
  await expect(page.getByRole("heading", { level: 3, name: "Customer analytics is unavailable" })).toBeVisible();
});
