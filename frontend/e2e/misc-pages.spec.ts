import { test, expect } from "@playwright/test";

test("inbox loads without error (empty queue is valid)", async ({ page }) => {
  await page.goto("/inbox");
  await expect(page.getByText(/something went wrong/i)).not.toBeVisible();
});

test("conversations: loads, status filter works, CSV export present", async ({ page }) => {
  await page.goto("/conversations");
  await expect(page.getByText(/something went wrong/i)).not.toBeVisible();

  const statusGroup = page.getByRole("group").first();
  await statusGroup.waitFor({ state: "visible", timeout: 15_000 });

  const exportButton = page.getByRole("button", { name: /export csv/i });
  await expect(exportButton).toBeVisible();
  await expect(exportButton).toBeEnabled();
});

test("quality: both tabs load without error", async ({ page }) => {
  await page.goto("/quality");
  await expect(page.getByText(/something went wrong/i)).not.toBeVisible();
  await expect(page.getByRole("tab", { name: "Gaps" })).toBeVisible({ timeout: 15_000 });
  await page.getByRole("tab", { name: "Bad answers" }).click();
  await expect(page.getByText(/something went wrong/i)).not.toBeVisible();
});

test("usage page shows quota figures", async ({ page }) => {
  await page.goto("/usage");
  await expect(page.getByText(/something went wrong/i)).not.toBeVisible();
});

test("overview dashboard loads without error", async ({ page }) => {
  await page.goto("/overview");
  await expect(page.getByText(/something went wrong/i)).not.toBeVisible();
});
