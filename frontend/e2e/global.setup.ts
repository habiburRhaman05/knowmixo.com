import { test as setup, expect } from "@playwright/test";

const EMAIL = "devhabib2005@gmail.com";
const PASSWORD = "pOIUUIOP2005$$";

setup("authenticate", async ({ page }) => {
  await page.goto("/login");
  const emailInput = page.getByPlaceholder("you@company.com");
  await emailInput.waitFor({ state: "visible", timeout: 20_000 });
  await emailInput.fill(EMAIL);
  await page.getByPlaceholder("Enter your password").fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/overview/, { timeout: 15_000 });
  await page.context().storageState({ path: "e2e/.auth/user.json" });
});
