import { test, expect } from "@playwright/test";

test.use({ storageState: { cookies: [], origins: [] } });

test("landing page renders and nav links work", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /only ever answers/i })).toBeVisible();
  await expect(page.getByRole("link", { name: "Pricing" }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Sign in" }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: /get started/i }).first()).toBeVisible();

  await page.getByRole("link", { name: "Pricing" }).first().click();
  await expect(page).toHaveURL(/\/pricing/);
});

test("pricing page renders live plan data without auth", async ({ page }) => {
  await page.goto("/pricing");
  await expect(page.getByRole("heading", { name: /simple pricing/i })).toBeVisible();

  // 5 monthly tiers.
  await expect(page.getByText("Free", { exact: true })).toBeVisible();
  await expect(page.getByText("Starter", { exact: true })).toBeVisible();
  await expect(page.getByText("Growth", { exact: true })).toBeVisible();
  await expect(page.getByText("Scale", { exact: true })).toBeVisible();
  await expect(page.getByText("Agency", { exact: true })).toBeVisible();

  // "$29" is a substring of "$299", so match the full "$N/mo" text to
  // disambiguate rather than using exact (the price and "/mo" are two
  // separate nodes inside the same <p>, so the element's full text is
  // never just "$29" alone either).
  await expect(page.getByText("$0/mo")).toBeVisible();
  await expect(page.getByText("$29/mo")).toBeVisible();
  await expect(page.getByText("$99/mo")).toBeVisible();
  await expect(page.getByText("$299/mo")).toBeVisible();
  await expect(page.getByText("$699/mo")).toBeVisible();

  await expect(page.getByRole("heading", { name: /frequently asked questions/i })).toBeVisible();
});
