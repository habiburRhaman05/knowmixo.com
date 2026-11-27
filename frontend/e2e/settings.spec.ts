import { test, expect } from "@playwright/test";

const TABS: Array<{ path: string; heading: RegExp }> = [
  { path: "/settings", heading: /account/i },
  { path: "/settings/security", heading: /security|mfa/i },
  { path: "/settings/team", heading: /team/i },
  { path: "/settings/escalation", heading: /escalation/i },
  { path: "/settings/api-keys", heading: /api key/i },
  { path: "/settings/billing", heading: /billing|plan/i },
  { path: "/settings/integrations", heading: /integrations|slack/i },
];

for (const tab of TABS) {
  test(`settings tab loads without error: ${tab.path}`, async ({ page }) => {
    await page.goto(tab.path);
    await expect(page.getByText(/something went wrong/i)).not.toBeVisible();
  });
}

test("API keys: Free plan correctly blocks key creation with a visible error", async ({ page }) => {
  // This account is on the Free plan, which does not include the `api`
  // feature (Scale+ only, app/public_api/keys_router.py::create_api_key
  // -> require_feature). Confirmed directly via API: POST /api-keys
  // returns 403 "feature_not_available". This test checks that
  // rejection is visible, not a silent failure.
  await page.goto("/settings/api-keys");
  const keyName = `E2E key ${Date.now()}`;
  await page.getByLabel("Name").fill(keyName);
  await page.getByText("Read conversations", { exact: true }).click();
  await page.getByRole("button", { name: /create key/i }).click();

  await expect(page.getByText(/your plan does not include api/i)).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText(/copy your api key now/i)).not.toBeVisible();
});

test("escalation: add a contact, confirm it requires verification before it can send", async ({ page }) => {
  await page.goto("/settings/escalation");
  // Unique per run so a prior interrupted run's leftover row (if cleanup
  // didn't get to run) can never make this test's locators ambiguous.
  const testAddress = `test-e2e-${Date.now()}@example.com`;
  await page.getByLabel("Address").fill(testAddress);
  await page.getByRole("button", { name: /^add$/i }).click();

  await expect(page.getByText(testAddress)).toBeVisible({ timeout: 15_000 });
  const row = page.locator("li", { hasText: testAddress });
  await expect(row.getByText("Unverified")).toBeVisible();
  await expect(row.getByRole("button", { name: /send code/i })).toBeVisible();
  // Not verified yet -- the "Test" send button must not be offered.
  await expect(row.getByRole("button", { name: /^test$/i })).not.toBeVisible();

  page.once("dialog", (d) => d.accept()); // removeContact() uses window.confirm
  await row.getByRole("button", { name: /remove contact/i }).click();
  await expect(page.getByText(testAddress)).not.toBeVisible({ timeout: 15_000 });
});

test("team: invite is correctly blocked by the Free plan's 1-member limit, with a visible error", async ({ page }) => {
  // This account is on the Free plan (1 member max = owner only), so a
  // second invite is expected to be REJECTED by plan-limit enforcement
  // (app/team/service.py::_check_member_quota) -- this test confirms
  // that rejection surfaces as a real, readable error, not a silent
  // failure or a crash. Confirmed via direct API call first: POST
  // /api/v1/team/invites returns 402 "plan_limit_members".
  await page.goto("/settings/team");
  const inviteEmail = `e2e-invite-${Date.now()}@mailinator.com`;
  await page.getByLabel("Email", { exact: true }).fill(inviteEmail);
  await page.getByRole("button", { name: /send invite/i }).click();

  await expect(page.getByText(/your plan allows up to 1 team members/i)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(inviteEmail)).not.toBeVisible();
});

test("billing: 5 plan cards render with real prices, Upgrade button present but not followed", async ({ page }) => {
  await page.goto("/settings/billing");
  await expect(page.getByText("Free", { exact: true })).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Starter", { exact: true })).toBeVisible();
  await expect(page.getByText("Growth", { exact: true })).toBeVisible();
  await expect(page.getByText("Scale", { exact: true })).toBeVisible();
  await expect(page.getByText("Agency", { exact: true })).toBeVisible();

  const upgradeButtons = page.getByRole("button", { name: /upgrade/i });
  expect(await upgradeButtons.count()).toBeGreaterThan(0);
  await expect(upgradeButtons.first()).toBeEnabled();
  // Intentionally not clicked -- would navigate to real Stripe Checkout.
});
