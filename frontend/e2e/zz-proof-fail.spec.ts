import { test, expect } from "@playwright/test";

test("deliberate failure proving CI gate (#49, do not merge)", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("this text does not exist")).toBeVisible({ timeout: 2000 });
});
