import { expect, test } from "@playwright/test";

test("loads the sample, shows the dashboard and updates it for a new date range", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Try sample data" }).click();
  await expect(page).toHaveURL(/\/d\/[^/]+$/);

  const keyFigures = page.getByRole("region", { name: "Key figures" });
  const labels = ["Gross sales", "Orders", "Units sold", "Average order value"];
  await expect(keyFigures.getByRole("term")).toHaveText(labels);
  const values = keyFigures.getByRole("definition");
  await expect(values).toHaveCount(4);
  for (const index of [0, 1, 2, 3]) {
    // A digit first: a card that is still loading has no text yet.
    await expect(values.nth(index)).toHaveText(/\d/);
    await expect(values.nth(index)).not.toHaveText(/^(0|\$0\.00)$/);
  }
  const grossSales = values.first();
  const before = await grossSales.innerText();

  const trend = page.getByRole("region", { name: "Sales trend" });
  await expect(trend.getByRole("heading", { name: "Gross sales — weekly" })).toBeVisible();
  await expect(trend.getByRole("img")).toBeVisible();

  const topProducts = page.getByRole("region", { name: "Top products" });
  await expect(topProducts.getByRole("img")).toBeVisible();
  const rows = topProducts.getByRole("table").locator("tbody").getByRole("row");
  await expect(rows).toHaveCount(10);

  await page.getByLabel("Start date").fill("2025-03-01");
  await page.getByLabel("End date").fill("2025-03-31");

  await expect(grossSales).not.toHaveText(before);
  await expect(trend.getByRole("heading", { name: "Gross sales — daily" })).toBeVisible();
  await expect(rows).toHaveCount(10);
});
