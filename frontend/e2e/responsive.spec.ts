import { expect, test } from "@playwright/test";

const widths = [360, 768, 1280] as const;

async function assertNoPageOverflow(page: import("@playwright/test").Page): Promise<void> {
  const dimensions = await page.evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
    bodyWidth: document.body.scrollWidth,
  }));
  expect(dimensions.documentWidth).toBeLessThanOrEqual(dimensions.viewportWidth);
  expect(dimensions.bodyWidth).toBeLessThanOrEqual(dimensions.viewportWidth);
}

async function assertControlTargets(page: import("@playwright/test").Page): Promise<void> {
  // Dismiss is intentionally a text-only action per the design system; all
  // form controls and primary/secondary buttons use the 40 px target.
  const controls = page.locator("button:visible:not([aria-label^='Dismiss']), input:not(.sr-only):visible, select:visible");
  for (let index = 0; index < await controls.count(); index += 1) {
    const box = await controls.nth(index).boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(40);
  }
}

test("the sample views fit phone, tablet and desktop widths without page overflow", async ({ page }) => {
  for (const width of widths) {
    await page.setViewportSize({ width, height: width === 360 ? 740 : 800 });
    await page.goto("/");
    await page.getByRole("button", { name: "Try sample data" }).click();
    await expect(page).toHaveURL(/\/d\/[^/]+$/);
    await expect(page.getByRole("heading", { level: 2, name: "Overview" })).toBeVisible();
    await assertNoPageOverflow(page);
    await assertControlTargets(page);

    await page.getByRole("link", { name: "Products" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "Products" })).toBeVisible();
    await assertNoPageOverflow(page);
    await assertControlTargets(page);

    const firstProduct = page.getByRole("region", { name: "Rankings" }).getByRole("row").nth(1).getByRole("link");
    await firstProduct.click();
    await expect(page.getByRole("region", { name: "Product detail" })).toBeVisible();
    await assertNoPageOverflow(page);
    await page.getByRole("link", { name: "All products" }).click();

    await page.getByRole("link", { name: "Customers" }).click();
    await expect(page.getByRole("heading", { level: 2, name: "Customers" })).toBeVisible();
    await assertNoPageOverflow(page);
    await assertControlTargets(page);
    const coverage = page.getByRole("region", { name: "Customer coverage" });
    const unavailable = page.getByRole("heading", { name: "Customer analytics is unavailable" });
    await expect.poll(async () => (await coverage.count()) + (await unavailable.count())).toBeGreaterThan(0);
    if (await coverage.count() > 0) {
      expect(await page.locator(".overflow-x-auto").count()).toBeGreaterThan(0);
    } else {
      await expect(unavailable).toBeVisible();
    }
  }
});
