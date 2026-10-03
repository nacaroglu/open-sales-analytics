import { expect, test } from "@playwright/test";
import { SAMPLE_KPIS, keyFigures, openSample } from "./helpers";

test("a date range changes the values and granularity and Reset restores them", async ({ page }) => {
  await openSample(page);
  const kpis = keyFigures(page);
  const trend = page.getByRole("region", { name: "Sales trend" });
  await expect(trend.getByRole("heading", { name: "Gross sales — weekly" })).toBeVisible();

  await page.getByLabel("Start date").fill("2025-03-01");
  await page.getByLabel("End date").fill("2025-03-31");
  await expect(kpis.grossSales).not.toHaveText(SAMPLE_KPIS.grossSales);
  await expect(kpis.orders).not.toHaveText(SAMPLE_KPIS.orders);
  await expect(trend.getByRole("heading", { name: "Gross sales — daily" })).toBeVisible();

  await page.getByRole("button", { name: "Reset" }).click();
  await expect(kpis.grossSales).toHaveText(SAMPLE_KPIS.grossSales);
  await expect(kpis.orders).toHaveText(SAMPLE_KPIS.orders);
  await expect(kpis.unitsSold).toHaveText(SAMPLE_KPIS.unitsSold);
  await expect(trend.getByRole("heading", { name: "Gross sales — weekly" })).toBeVisible();
  await expect(page.getByLabel("Start date")).toHaveValue("2025-01-01");
  await expect(page.getByLabel("End date")).toHaveValue("2025-12-31");
});
