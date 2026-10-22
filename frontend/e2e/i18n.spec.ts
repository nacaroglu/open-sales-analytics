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

  const apiRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/")) apiRequests.push(request.url());
  });
  const requestCountBeforeSwitch = apiRequests.length;
  const activeUrl = page.url();
  await page.getByLabel("Dil").selectOption("en");
  await expect(page.getByRole("heading", { level: 2, name: "Overview" })).toBeVisible();
  await expect(page.getByLabel("Start date")).toHaveValue("2025-01-01");
  await expect(page.getByLabel("End date")).toHaveValue("2025-12-31");
  expect(page.url()).toBe(activeUrl);
  expect(apiRequests.length).toBe(requestCountBeforeSwitch);

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

test("each additional language completes a translated dashboard, product and customer journey", async ({ page }) => {
  const packs = [
    { locale: "de", overview: "Übersicht", period: "1. Jan. 2024 bis 31. Dez. 2025", products: "Produkte", rankings: "Ranglisten", allProducts: "Alle Produkte", customers: "Kunden", coverage: "Kundenabdeckung", retention: "Kohortenbindungstabelle", monthZero: "Monat 0", median: /Median:/, price: /Gewichteter Stückpreis/ },
    { locale: "ru", overview: "Обзор", period: "1 янв. 2024 г. — 31 дек. 2025 г.", products: "Товары", rankings: "Рейтинги", allProducts: "Все товары", customers: "Клиенты", coverage: "Охват клиентов", retention: "Таблица удержания когорт", monthZero: "Месяц 0", median: /Медиана:/, price: /Средневзвешенная цена/ },
    { locale: "es", overview: "Resumen", period: "1 ene 2024 a 31 dic 2025", products: "Productos", rankings: "Clasificaciones", allProducts: "Todos los productos", customers: "Clientes", coverage: "Cobertura de clientes", retention: "Tabla de retención de cohortes", monthZero: "Mes 0", median: /Mediana:/, price: /Precio unitario ponderado/ },
    { locale: "zh-CN", overview: "概览", period: "2024年1月1日 至 2025年12月31日", products: "商品", rankings: "排行榜", allProducts: "所有商品", customers: "客户", coverage: "客户覆盖率", retention: "队列留存表", monthZero: "第 0 月", median: /中位数：/, price: /加权单价/ },
    { locale: "ja", overview: "概要", period: "2024年1月1日～2025年12月31日", products: "商品", rankings: "ランキング", allProducts: "すべての商品", customers: "顧客", coverage: "顧客カバー率", retention: "コホート継続率の表", monthZero: "0か月目", median: /中央値：/, price: /加重平均単価/ },
  ] as const;

  await page.goto("/");
  await page.getByRole("button", { name: "Örnek veriyi dene" }).click();
  await expect(page).toHaveURL(/\/d\/[^/]+$/);

  const apiRequests: string[] = [];
  let filterApplied = false;
  page.on("request", (request) => {
    if (request.url().includes("/api/")) apiRequests.push(request.url());
  });

  for (const pack of packs) {
    const urlBeforeSwitch = page.url();
    const requestsBeforeSwitch = apiRequests.length;
    await page.locator("header select").selectOption(pack.locale);
    await expect(page.locator("html")).toHaveAttribute("lang", pack.locale);
    await expect(page.getByRole("heading", { level: 2, name: pack.overview, exact: true })).toBeVisible();
    await expect(page.locator('input[type="date"]').nth(0)).toHaveValue(filterApplied ? "2025-01-01" : "2024-01-01");
    await expect(page.locator('input[type="date"]').nth(1)).toHaveValue("2025-12-31");
    await expect(page.getByText(pack.period, { exact: true })).toBeVisible();
    expect(page.url()).toBe(urlBeforeSwitch);
    expect(apiRequests.length, `language switch made API requests: ${apiRequests.slice(requestsBeforeSwitch).join(", ")}`).toBe(requestsBeforeSwitch);

    await page.getByRole("link", { name: pack.products, exact: true }).click();
    await expect(page.getByRole("region", { name: pack.rankings })).toBeVisible();
    const rankings = page.getByRole("region", { name: pack.rankings });
    const firstProduct = rankings.getByRole("row").nth(1).getByRole("link");
    const productName = await firstProduct.innerText();
    await firstProduct.click();
    await expect(page.getByRole("heading", { level: 2, name: productName })).toBeVisible();
    await expect(page.getByRole("img", { name: pack.price })).toBeVisible();

    await page.getByRole("link", { name: pack.allProducts, exact: true }).click();
    await page.getByRole("link", { name: pack.customers, exact: true }).click();
    await expect(page.getByRole("region", { name: pack.coverage })).toBeVisible();
    const retention = page.getByRole("table", { name: pack.retention });
    await expect(retention).toBeVisible();
    await expect(retention.getByRole("columnheader", { name: pack.monthZero, exact: true })).toBeVisible();
    await expect(page.getByText(pack.median)).toBeVisible();
    await page.reload();
    await expect(page.locator("html")).toHaveAttribute("lang", pack.locale);
    await expect(page.getByRole("heading", { level: 2, name: pack.customers, exact: true })).toBeVisible();
    await expect(page).toHaveURL(/\/d\/[^/]+\/customers$/);

    await page.getByRole("link", { name: pack.overview, exact: true }).click();
    await expect(page.getByRole("heading", { level: 2, name: pack.overview, exact: true })).toBeVisible();
    const filteredOverview = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname.endsWith("/overview") && url.searchParams.get("start") === "2025-01-01" && response.ok();
    });
    await page.locator('input[type="date"]').nth(0).fill("2025-01-01");
    await filteredOverview;
    filterApplied = true;
  }
});
