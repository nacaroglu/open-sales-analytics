import { expect, test } from "@playwright/test";

test.use({ locale: "tr-TR" });

test("browser Turkish is detected, English can be selected and persists across navigation and reload", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("lang", "tr");
  await expect(page.getByLabel("Dil")).toHaveValue("tr");
  await expect(page.getByRole("button", { name: "Örnek veriyi dene" })).toBeVisible();

  await page.getByLabel("Dil").selectOption("en");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await page.getByRole("button", { name: "Try sample data" }).click();
  await expect(page).toHaveURL(/\/d\/[^/]+$/);
  await expect(page.getByLabel("Language")).toHaveValue("en");
  await page.reload();
  await expect(page.getByLabel("Language")).toHaveValue("en");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
});

test("switching language preserves the active route, filters and loaded data across journeys", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Örnek veriyi dene" }).click();
  await expect(page).toHaveURL(/\/d\/[^/]+$/);
  await expect(page.getByRole("heading", { level: 2, name: "Genel bakış" })).toBeVisible();
  await page.getByLabel("Başlangıç tarihi").fill("2025-01-01");
  await page.getByLabel("Bitiş tarihi").fill("2025-12-31");
  await page.getByLabel("Şununla karşılaştır").selectOption("previous_year");
  await expect(page.getByLabel("Bitiş tarihi")).toHaveValue("2025-12-31");

  let apiRequests = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/")) apiRequests += 1;
  });
  const requestCountBeforeSwitch = apiRequests;
  const activeUrl = page.url();
  await page.getByLabel("Dil").selectOption("en");
  await expect(page.getByRole("heading", { level: 2, name: "Overview" })).toBeVisible();
  await expect(page.getByLabel("Start date")).toHaveValue("2025-01-01");
  await expect(page.getByLabel("End date")).toHaveValue("2025-12-31");
  expect(page.url()).toBe(activeUrl);
  expect(apiRequests).toBe(requestCountBeforeSwitch);

  await page.getByRole("link", { name: "Products" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Products" })).toBeVisible();
  const rankings = page.getByRole("region", { name: "Rankings" });
  const firstProduct = rankings.getByRole("row").nth(1).getByRole("link");
  const productName = await firstProduct.innerText();
  await firstProduct.click();
  await expect(page.getByRole("heading", { level: 2, name: productName })).toBeVisible();
  await page.getByLabel("Language").selectOption("tr");
  await expect(page.getByRole("link", { name: "Tüm ürünler" })).toBeVisible();
  await expect(page.getByRole("heading", { level: 2, name: productName })).toBeVisible();
  await expect(page.getByRole("img", { name: /ağırlıklı birim fiyat/i })).toBeVisible();

  await page.getByRole("link", { name: "Tüm ürünler" }).click();
  await page.getByRole("link", { name: "Müşteriler" }).click();
  await expect(page.getByRole("heading", { level: 2, name: "Müşteriler" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Müşteri kapsamı" })).toBeVisible();
  await expect(page.getByRole("table", { name: "Kohort elde tutma tablosu" })).toBeVisible();
});
