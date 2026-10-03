import { expect, test } from "@playwright/test";
import { SAMPLE_KPIS, keyFigures, openSample } from "./helpers";

test("Try sample data opens a populated dashboard", async ({ page }) => {
  await openSample(page);

  const figures = page.getByRole("region", { name: "Key figures" });
  await expect(figures.getByRole("term")).toHaveText([
    "Gross sales",
    "Orders",
    "Units sold",
    "Average order value",
  ]);
  const kpis = keyFigures(page);
  await expect(kpis.orders).toHaveText(SAMPLE_KPIS.orders);
  await expect(kpis.unitsSold).toHaveText(SAMPLE_KPIS.unitsSold);
  await expect(kpis.averageOrderValue).toHaveText(SAMPLE_KPIS.averageOrderValue);

  const trend = page.getByRole("region", { name: "Sales trend" });
  await expect(trend.getByRole("heading", { name: "Gross sales — weekly" })).toBeVisible();
  await expect(trend.getByRole("img")).toBeVisible();

  const topProducts = page.getByRole("region", { name: "Top products" });
  await expect(topProducts.getByRole("img")).toBeVisible();
  await expect(topProducts.getByRole("table").locator("tbody").getByRole("row")).toHaveCount(10);
});
