import { test, expect } from "@playwright/test";

test("dashboard loads", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Band A")).toBeVisible();
  await expect(page.getByText("Entry Points")).toBeVisible();
});
