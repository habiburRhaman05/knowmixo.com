import { test, expect } from "@playwright/test";

// This file intentionally runs with a clean, unauthenticated context --
// the global setup's session must not leak in here.
test.use({ storageState: { cookies: [], origins: [] } });

const EMAIL = "devhabib2005@gmail.com";
const PASSWORD = "pOIUUIOP2005$$";

test("valid login succeeds and lands on /overview", async ({ page }) => {
  await page.goto("/login");
  await page.getByPlaceholder("you@company.com").waitFor({ state: "visible" });
  await page.getByPlaceholder("you@company.com").fill(EMAIL);
  await page.getByPlaceholder("Enter your password").fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/overview/, { timeout: 15_000 });
});

test("invalid password shows a visible error and stays on /login", async ({ page }) => {
  await page.goto("/login");
  await page.getByPlaceholder("you@company.com").waitFor({ state: "visible" });
  await page.getByPlaceholder("you@company.com").fill(EMAIL);
  await page.getByPlaceholder("Enter your password").fill("DefinitelyWrongPassword123!");
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page.getByText(/incorrect email or password/i)).toBeVisible({ timeout: 20_000 });
  await expect(page).toHaveURL(/\/login/);
});

test("logout clears the session and returns to /login", async ({ page }) => {
  await page.goto("/login");
  await page.getByPlaceholder("you@company.com").waitFor({ state: "visible" });
  await page.getByPlaceholder("you@company.com").fill(EMAIL);
  await page.getByPlaceholder("Enter your password").fill(PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/overview/, { timeout: 15_000 });

  await page.getByRole("button", { name: /open account menu/i }).click();
  await page.getByText("Sign out").click();
  await expect(page).toHaveURL(/\/login/, { timeout: 20_000 });

  // A protected page must now bounce back to /login.
  await page.goto("/overview");
  await expect(page).toHaveURL(/\/login/);
});
