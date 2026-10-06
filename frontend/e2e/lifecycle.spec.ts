import { expect, test } from "@playwright/test";
import { openSample } from "./helpers";

test("Analyze another file returns to upload and the prior dataset is gone", async ({ page }) => {
  await openSample(page);
  const dashboardUrl = page.url();
  const session = await page.evaluate(() => window.sessionStorage.getItem("osa.session"));
  expect(session).not.toBeNull();

  await page.getByRole("button", { name: "Analyze another file" }).click();
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "Start an analysis" })).toBeVisible();

  // Even with the old token put back, the server no longer has the dataset.
  await page.evaluate((value) => window.sessionStorage.setItem("osa.session", value ?? ""), session);
  await page.goto(dashboardUrl);
  await expect(page.getByRole("heading", { name: "This dataset has expired or was deleted" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Go to the upload screen" })).toBeVisible();
});

// A real expiry: the server under test runs with DATASET_TTL_SECONDS=60 (see playwright.config.ts;
// start a container with `-e DATASET_TTL_SECONDS=60`). The dataset is created for real and the page
// is reloaded, bounded, until the server itself answers 404 for it. No fixed sleep.
test("an expired dataset shows the expired experience", async ({ page }) => {
  test.setTimeout(150_000);
  await openSample(page);
  await expect(
    page.getByRole("region", { name: "Date range" }),
    "the server must run with DATASET_TTL_SECONDS=60",
  ).toContainText("Expires in less than a minute");

  const expired = page.getByRole("heading", { name: "This dataset has expired or was deleted" });
  await expect(async () => {
    await page.reload();
    await expect(expired).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 120_000, intervals: [2_000] });

  await expect(page.getByText("Upload a file or try the sample data again.")).toBeVisible();
  await page.getByRole("link", { name: "Go to the upload screen" }).click();
  await expect(page.getByRole("button", { name: "Try sample data" })).toBeVisible();
});
