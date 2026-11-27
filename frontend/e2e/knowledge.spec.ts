import { test, expect, type Page } from "@playwright/test";

const TEXT_TITLE = `E2E text source ${Date.now()}`;
const FAQ_TITLE = `E2E FAQ source ${Date.now()}`;

async function openAddSourceDialog(page: Page) {
  await page.getByRole("button", { name: /add source/i }).click();
  await expect(page.getByRole("heading", { name: /add a knowledge source/i })).toBeVisible();
}

test.describe.serial("knowledge sources", () => {
  test("add a text source", async ({ page }) => {
    await page.goto("/knowledge");
    await openAddSourceDialog(page);
    await page.getByRole("tab", { name: "Paste text" }).click();
    await page.getByLabel("Title").fill(TEXT_TITLE);
    await page.getByLabel("Content").fill("This is throwaway E2E test content for automated testing.");
    await page.getByRole("button", { name: /add text source/i }).click();

    await expect(page.getByText(/text source queued/i).first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(TEXT_TITLE)).toBeVisible({ timeout: 30_000 });
  });

  test("add an FAQ source", async ({ page }) => {
    await page.goto("/knowledge");
    await openAddSourceDialog(page);
    await page.getByRole("tab", { name: "FAQ" }).click();
    await page.getByLabel("Title").fill(FAQ_TITLE);
    await page.getByLabel("Question").fill("What are your hours?");
    await page.getByLabel("Answer").fill("We are open 9 to 5, Monday to Friday.");
    await page.getByRole("button", { name: /add faq source/i }).click();

    await expect(page.getByText(/faq source queued/i).first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(FAQ_TITLE)).toBeVisible({ timeout: 30_000 });
  });

  test("search filters the source list", async ({ page }) => {
    await page.goto("/knowledge");
    await page.getByLabel("Search sources").fill(TEXT_TITLE);
    await expect(page.getByText(TEXT_TITLE)).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(FAQ_TITLE)).not.toBeVisible();
  });

  test("open detail view, disable then re-enable a source", async ({ page }) => {
    await page.goto("/knowledge");
    await page.getByLabel("Search sources").fill(TEXT_TITLE);
    await page.getByText(TEXT_TITLE).first().click();
    // Detail panel should show the same title.
    await expect(page.getByText(TEXT_TITLE).last()).toBeVisible();
    // The detail panel is a fixed-position overlay that intercepts clicks
    // on the row underneath -- close it before interacting with the row.
    await page.getByRole("button", { name: /close source detail/i }).click();

    const row = page.locator("li", { hasText: TEXT_TITLE });
    await row.getByRole("button", { name: /more actions/i }).click();
    await page.getByText("Disable source").click();
    await expect(page.getByText(/source disabled/i).first()).toBeVisible({ timeout: 30_000 });
    await expect(row.getByText("Disabled")).toBeVisible();

    await row.getByRole("button", { name: /more actions/i }).click();
    await page.getByText("Enable source").click();
    await expect(page.getByText(/source re-enabled/i).first()).toBeVisible({ timeout: 30_000 });
  });

  test("clean up: delete both test sources", async ({ page }) => {
    await page.goto("/knowledge");
    await page.getByLabel("Search sources").fill("E2E ");
    for (const title of [TEXT_TITLE, FAQ_TITLE]) {
      const row = page.locator("li", { hasText: title });
      if (await row.count()) {
        await row.getByRole("button", { name: /more actions/i }).click();
        page.once("dialog", (d) => d.accept());
        await page.getByText("Delete source").click();
        await expect(page.getByText(/source deleted/i).first()).toBeVisible({ timeout: 30_000 });
      }
    }
    await page.getByLabel("Search sources").fill("E2E ");
    await expect(page.getByText(TEXT_TITLE)).not.toBeVisible();
    await expect(page.getByText(FAQ_TITLE)).not.toBeVisible();
  });
});
