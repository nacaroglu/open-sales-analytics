import { expect, test } from "@playwright/test";
import { SAMPLE_KPIS, keyFigures } from "./helpers";

// The test server runs with uploads on, so the page is shown a demo-mode
// /api/config; the real 403 upload_disabled is covered by backend/tests/test_demo_mode.py.
test("in demo mode the sample dashboard opens and the page offers no upload controls", async ({ page }) => {
  await page.route("**/api/config", (route) =>
    route.fulfill({
      json: { public_demo_mode: true, max_upload_bytes: 52428800, max_rows: 500000 },
    }),
  );
  await page.goto("/");

  await expect(page.getByText("This demo accepts sample data only.")).toBeVisible();
  await expect(page.getByLabel("CSV file")).toHaveCount(0);
  await expect(page.getByLabel("Currency")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Upload" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Download sample CSV" })).toBeVisible();

  const link = page.getByRole("link", { name: "Run it yourself with Docker" });
  await expect(link).toHaveAttribute(
    "href",
    "https://github.com/nacaroglu/open-sales-analytics#run-it-with-docker",
  );
  await link.focus();
  await expect(link).toBeFocused();

  await page.getByRole("button", { name: "Try sample data" }).click();
  await expect(page).toHaveURL(/\/d\/[^/]+$/);
  await expect(keyFigures(page).grossSales).toHaveText(SAMPLE_KPIS.grossSales);
  await expect(page.getByRole("region", { name: "Sales trend" }).getByRole("img")).toBeVisible();
  await expect(page.getByRole("region", { name: "Top products" }).getByRole("table")).toBeVisible();
});
