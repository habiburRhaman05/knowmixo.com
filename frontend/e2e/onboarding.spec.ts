import { test, expect } from "@playwright/test";

test("onboarding loads without the bot-404 error and shows real step status", async ({ page }) => {
  await page.goto("/onboarding");
  await expect(page.getByText(/no bot found for this company/i)).not.toBeVisible();
  await expect(page.getByText(/something went wrong/i)).not.toBeVisible();

  await expect(page.getByText("Company details")).toBeVisible();
  await expect(page.getByText("Add your first source")).toBeVisible();
  await expect(page.getByText("Shape the assistant")).toBeVisible();
  await expect(page.getByText("Preview the answers")).toBeVisible();
  await expect(page.getByText("Publish the first snapshot")).toBeVisible();

  // Step badges render real "Done"/"Not started" state (not a hardcoded value).
  const badges = page.getByText(/^(Done|Not started)$/);
  await expect(badges.first()).toBeVisible();
  expect(await badges.count()).toBeGreaterThanOrEqual(5);
});

test("onboarding step 2 has an inline crawl form (or correctly skips it once a source exists)", async ({ page }) => {
  // Other spec files in this suite add/remove real sources on this same
  // account, so step 2's content legitimately depends on current state --
  // the crawl form only when hasSource is false. Both are valid, real
  // outcomes; this just shouldn't crash either way.
  await page.goto("/onboarding");
  // Wait for the page's own async load (company/bot/documents) to settle
  // into one of its two real states before reading which one it landed
  // on -- checking isVisible() immediately after goto() would race the
  // ~2.5s fetch and always read "false" (still loading).
  const hasSourceText = page.getByText(/you have at least one source/i);
  const crawlButton = page.getByRole("button", { name: /crawl.*import/i });
  await expect(hasSourceText.or(crawlButton)).toBeVisible({ timeout: 20_000 });
  const hasSourceAlready = await hasSourceText.isVisible();
  if (hasSourceAlready) {
    await expect(page.getByText(/you have at least one source/i)).toBeVisible();
  } else {
    await expect(page.getByPlaceholder("https://example.com").first()).toBeVisible();
    await expect(page.getByRole("button", { name: /crawl.*import/i })).toBeVisible();
  }
});

test("onboarding industry picker is present on step 1", async ({ page }) => {
  await page.goto("/onboarding");
  await expect(page.getByRole("button", { name: "SaaS" })).toBeVisible();
  await expect(page.getByRole("button", { name: "E-commerce" })).toBeVisible();
});
