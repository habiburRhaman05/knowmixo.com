import { test, expect } from "@playwright/test";

test("chatbot studio: form is gated behind loading, no edit-before-load race", async ({ page }) => {
  // Regression test for a real bug the earlier run found: the form used
  // to render immediately with DEFAULT_CONFIG placeholder values
  // (editable right away), then the async GET /api/bff/bot resolved and
  // unconditionally overwrote local draft state -- silently discarding
  // anything typed in that window. Fixed by gating the whole form behind
  // a `loading` state. Assert that gate directly: immediately after
  // navigation (before the GET resolves), the real name input must NOT
  // be in the DOM at all -- only once loading completes does it appear.
  await page.goto("/chatbot");
  const nameInput = page.locator('input[placeholder="Acme Support"]');
  await expect(nameInput).not.toBeAttached();
  await expect(page.getByText(/something went wrong/i)).not.toBeVisible();

  await nameInput.waitFor({ state: "visible", timeout: 15_000 });
  await nameInput.fill("E2E Test Bot");

  // Plain role template pill.
  await page.getByRole("button", { name: "Customer support" }).click();
  // Industry starter pill (sets instructions + greeting + suggestions together).
  await page.getByRole("button", { name: "SaaS" }).click();

  await expect(page.getByText("Unsaved changes")).toBeVisible();
  const saveButton = page.getByRole("button", { name: /save draft/i });
  await expect(saveButton).toBeEnabled();
  await saveButton.click();
  await expect(page.getByText(/draft saved/i).first()).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Unsaved changes")).not.toBeVisible();

  // Live preview panel actually gets a reply (LLM call -- can be slow).
  // It streams: a "typing" indicator appears while generating, then
  // disappears once the reply is complete -- a real round trip, not just
  // "the input exists".
  const message = page.getByLabel("Message");
  await message.waitFor({ state: "visible" });
  await message.fill("What can you help me with?");
  await page.getByRole("button", { name: /send message/i }).click();
  const typing = page.getByLabel(/assistant is typing/i);
  await expect(typing).toBeVisible({ timeout: 15_000 });
  await expect(typing).not.toBeVisible({ timeout: 60_000 });
});

test("chatbot publish page loads", async ({ page }) => {
  await page.goto("/chatbot/publish");
  await expect(page.getByText(/something went wrong/i)).not.toBeVisible();
  await expect(page.getByRole("heading", { name: /publish/i }).first()).toBeVisible({ timeout: 15_000 });
});

test("playground loads without error", async ({ page }) => {
  await page.goto("/playground");
  await expect(page.getByText(/something went wrong/i)).not.toBeVisible();
});
