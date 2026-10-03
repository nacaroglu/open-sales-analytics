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

// The server's clock cannot be moved from the browser (and a container's settings cannot be
// changed), and DATASET_TTL_HOURS is whole hours, so a real expiry would take an hour at least.
// The dataset is real; once it is open the server's own answer for an expired dataset (404
// not_found, the same body as backend/tests/test_auth.py checks) is served for every call about it.
test("an expired dataset shows the expired experience", async ({ page }) => {
  await openSample(page);

  await page.route("**/api/datasets/*/**", (route) =>
    route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "not_found", message: "The dataset was not found." } }),
    }),
  );
  await page.reload();

  await expect(page.getByRole("heading", { name: "This dataset has expired or was deleted" })).toBeVisible();
  await expect(page.getByText("Upload a file or try the sample data again.")).toBeVisible();
  await page.getByRole("link", { name: "Go to the upload screen" }).click();
  await expect(page.getByRole("button", { name: "Try sample data" })).toBeVisible();
});
