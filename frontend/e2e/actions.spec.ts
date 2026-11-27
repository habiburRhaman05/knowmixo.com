import { test, expect } from "@playwright/test";

test("actions: create and delete an HTTP action", async ({ page }) => {
  // Regression test for a real bug the earlier run found: createAction()
  // used to silently no-op (no toast, no error) if the page's async GET
  // /api/bff/bot hadn't resolved into local `botId` state yet. Fixed by
  // disabling (+loading) the "New action" button until botId resolves.
  // Assert that directly: immediately after navigation the button must
  // be disabled, then become enabled once the bot data has loaded.
  await page.goto("/actions");
  const newActionButton = page.getByRole("button", { name: /new action/i });
  await expect(newActionButton).toBeDisabled();
  await expect(page.getByText(/no bot found for this company/i)).not.toBeVisible();
  await expect(page.getByText(/something went wrong/i)).not.toBeVisible();

  await expect(newActionButton).toBeEnabled({ timeout: 15_000 });
  const actionName = `E2E action ${Date.now()}`;
  await newActionButton.click();
  await page.getByLabel("Name").fill(actionName);
  await page.getByLabel("URL").fill("https://httpbin.org/post");
  await page.getByRole("button", { name: /create action/i }).click();

  await expect(page.getByText(actionName)).toBeVisible({ timeout: 20_000 });

  const card = page.locator(".space-y-3 > div", { hasText: actionName });
  page.once("dialog", (d) => d.accept()); // removeAction() uses window.confirm
  await card.getByRole("button", { name: /delete action/i }).click();
  await expect(page.getByText(actionName)).not.toBeVisible({ timeout: 20_000 });
});
