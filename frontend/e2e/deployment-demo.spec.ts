import { expect, test } from "@playwright/test";
import { SAMPLE_KPIS, keyFigures } from "./helpers";

test("production demo serves a usable sample dashboard through Caddy", async ({ page, request }) => {
  test.skip(!process.env.E2E_BASE_URL, "Production Caddy smoke is the only runner for this journey.");

  const configResponse = await request.get("/api/config");
  expect(configResponse.ok()).toBeTruthy();
  expect(await configResponse.json()).toMatchObject({ public_demo_mode: true });

  await page.goto("/");
  await expect(page.getByText("This demo accepts sample data only.")).toBeVisible();
  await expect(page.getByLabel("CSV file")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Upload" })).toHaveCount(0);

  await page.getByRole("button", { name: "Try sample data" }).click();
  await expect(page).toHaveURL(/\/d\/[^/]+$/);
  await expect(keyFigures(page).grossSales).toHaveText(SAMPLE_KPIS.grossSales);
  await expect(keyFigures(page).orders).toHaveText(SAMPLE_KPIS.orders);
  await expect(
    page
      .getByRole("region", { name: "Sales trend" })
      .getByRole("img", { name: /^(Daily|Weekly|Monthly) gross sales from/ }),
  ).toBeVisible();
  await expect(page.getByRole("region", { name: "Top products" }).getByRole("table")).toBeVisible();
});
