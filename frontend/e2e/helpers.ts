import { expect } from "@playwright/test";
import type { Locator, Page } from "@playwright/test";

export const SAMPLE_KPIS = {
  grossSales: "$686,669.10",
  orders: "10,000",
  unitsSold: "24,340",
  averageOrderValue: "$68.67",
};

// A small file whose figures can be checked by hand: 3 orders, 7 units, 47.50 gross.
export const VALID_CSV = [
  "order_id,order_date,product_id,product_name,quantity,unit_price",
  "A1,2025-01-10,P1,Mug,2,10.00",
  "A1,2025-01-10,P2,Bag,1,5.50",
  "A2,2025-01-11,P1,Mug,1,10.00",
  "A3,2025-02-20,P3,Hat,3,4.00",
  "",
].join("\n");

export function keyFigures(page: Page): Record<"grossSales" | "orders" | "unitsSold" | "averageOrderValue", Locator> {
  const values = page.getByRole("region", { name: "Key figures" }).getByRole("definition");
  return {
    grossSales: values.nth(0),
    orders: values.nth(1),
    unitsSold: values.nth(2),
    averageOrderValue: values.nth(3),
  };
}

export async function chooseFile(page: Page, name: string, content: string, currency: string): Promise<void> {
  await page.getByLabel("CSV file").setInputFiles({
    name,
    mimeType: "text/csv",
    buffer: Buffer.from(content),
  });
  await page.getByLabel("Currency").selectOption(currency);
}

export async function openSample(page: Page): Promise<void> {
  await page.goto("/");
  await page.getByRole("button", { name: "Try sample data" }).click();
  await expect(page).toHaveURL(/\/d\/[^/]+$/);
  await expect(keyFigures(page).grossSales).toHaveText(SAMPLE_KPIS.grossSales);
}
