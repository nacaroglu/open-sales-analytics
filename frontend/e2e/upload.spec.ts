import { expect, test } from "@playwright/test";
import { VALID_CSV, chooseFile, keyFigures } from "./helpers";

test("a valid CSV with a currency opens the dashboard with the expected figures", async ({ page }) => {
  await page.goto("/");
  await chooseFile(page, "valid.csv", VALID_CSV, "EUR");
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page).toHaveURL(/\/d\/[^/]+$/);

  const kpis = keyFigures(page);
  await expect(kpis.grossSales).toHaveText("€47.50");
  await expect(kpis.orders).toHaveText("3");
  await expect(kpis.unitsSold).toHaveText("7");
  await expect(kpis.averageOrderValue).toHaveText("€15.83");

  const dates = page.getByRole("region", { name: "Date range" });
  await expect(dates).toContainText("2025-01-10 to 2025-02-20");
  await expect(dates).toContainText("EUR");

  const trend = page.getByRole("region", { name: "Sales trend" });
  await expect(trend.getByRole("heading", { name: "Gross sales — daily" })).toBeVisible();
  await expect(trend.getByRole("img")).toBeVisible();
  const topProducts = page.getByRole("region", { name: "Top products" });
  await expect(topProducts.getByRole("img")).toBeVisible();
  // Mug (3 units, 30.00) leads Hat (3 units, 12.00) and Bag (1 unit, 5.50).
  const rows = topProducts.getByRole("table").locator("tbody").getByRole("row");
  await expect(rows).toHaveCount(3);
  await expect(rows.first()).toContainText("Mug");
});

test("an invalid CSV stays on the upload screen and shows the code, row and field", async ({ page }) => {
  const invalid = [
    "order_id,order_date,product_id,product_name,quantity,unit_price",
    "A1,2025-01-10,P1,Mug,2,10.00",
    "A2,2025-01-11,P1,Mug,0,10.00",
    "",
  ].join("\n");
  await page.goto("/");
  await chooseFile(page, "invalid.csv", invalid, "USD");
  await page.getByRole("button", { name: "Upload" }).click();

  const report = page.getByRole("region", { name: "Validation report" });
  await expect(report).toContainText("The file was rejected and nothing was imported: 1 error to fix.");
  const row = report.getByRole("table", { name: "Errors" }).locator("tbody").getByRole("row");
  await expect(row).toHaveCount(1);
  const cells = row.getByRole("cell");
  await expect(cells.nth(0)).toHaveText("3");
  await expect(cells.nth(1)).toHaveText("quantity");
  await expect(cells.nth(2)).toHaveText("invalid_quantity");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("button", { name: "Upload" })).toBeVisible();
});
