import { expect, test } from "@playwright/test";
import { chooseFile } from "./helpers";

const CSV = [
  "order_id,order_date,product_id,product_name,quantity,unit_price",
  ...Array.from({ length: 10 }, (_, index) => `O${index + 1},2025-03-${String(index + 1).padStart(2, "0")},A,Alpha,1,10.00`),
  ...Array.from({ length: 10 }, (_, index) => `O${index + 1},2025-03-${String(index + 1).padStart(2, "0")},B,Beta,1,5.00`),
  "OLD,2025-01-01,C, Dormant,1,2.00",
  "",
].join("\n");

test("the Products journey covers rankings, dormancy and product detail", async ({ page }) => {
  await page.goto("/");
  await chooseFile(page, "products.csv", CSV, "USD");
  await page.getByRole("button", { name: "Upload" }).click();
  await expect(page).toHaveURL(/\/d\/[^/]+$/);
  await page.getByRole("link", { name: "Products" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Products" })).toBeVisible();

  const rankings = page.getByRole("region", { name: "Rankings" });
  await expect(rankings.getByRole("row", { name: /Alpha/ })).toBeVisible();
  await page.getByLabel("Inactive for").selectOption("30");
  await expect(page.getByRole("region", { name: "Dormant products" }).getByRole("row", { name: /Dormant/ })).toBeVisible();

  await rankings.getByRole("link", { name: "Alpha" }).click();
  await expect(page).toHaveURL(/\/products\/detail\?product_id=A$/);
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
  await expect(page.getByRole("img", { name: /Weighted unit price/ })).toBeVisible();
  await expect(page.getByRole("link", { name: "Beta" })).toBeVisible();
  await page.getByRole("link", { name: "All products" }).click();
  await expect(page).toHaveURL(/\/products$/);
});
