import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fixture from "../fixtures/guidance-event.json";

test("patient directory exposes search, compact rows, sorting, paging and removable filters", async ({ page }) => {
  const origin = new URL(process.env.E2E_BASE_URL || "http://localhost:3000").origin;
  const patients = Array.from({ length: 28 }, (_, i) => ({ ...fixture.profileSnapshot, id: `explicit-fixture-${i}`, displayName: `Synthetic Patient ${String(i + 1).padStart(2, "0")}`, note: "Synthetic café and television note", eventCount: i, latestStatus: i ? "ready" : undefined, followUpDate: `2026-09-${String(28 - i).padStart(2, "0")}` }));
  const searches: URL[] = [];
  await page.route("**/*", (route) => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  await page.route("**/api/**", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/session") return route.fulfill({ json: { workspaceId: "explicit-ui-fixture", patient: null } });
    if (url.pathname === "/api/patients") {
      searches.push(url);
      return route.fulfill({ json: { patients: url.searchParams.get("q") || url.searchParams.get("status") || url.searchParams.get("followUp") ? [] : patients } });
    }
    return route.abort();
  });
  await page.goto("/clinic");
  await expect(page.locator(".clinic-patient-row")).toHaveCount(25);
  await expect(page.getByText("28 patients", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Result status")).toHaveCount(0);
  await expect(page.getByRole("searchbox")).toBeVisible();
  await page.getByLabel("Sort by").selectOption("moments");
  await expect(page.locator(".clinic-patient-name strong").first()).toHaveText("Synthetic Patient 28");
  await page.getByLabel("Sort by").selectOption("name");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.locator(".clinic-patient-row")).toHaveCount(3);
  await expect(page.getByText("26–28 of 28", { exact: true })).toBeVisible();
  await page.getByLabel("Sort by").selectOption("followUp");
  await expect(page.locator(".clinic-patient-name strong").first()).toHaveText("Synthetic Patient 28");
  await page.getByRole("button", { name: "Filters", exact: true }).click();
  await page.getByLabel("Follow-up date", { exact: true }).fill("2026-09-21");
  await expect(page.getByRole("heading", { name: "No matching patients" })).toBeVisible();
  expect(searches.at(-1)?.searchParams.get("followUp")).toBe("2026-09-21");
  await page.getByRole("button", { name: "Clear search & filters", exact: true }).first().click();
  await expect(page.locator(".clinic-patient-row")).toHaveCount(25);
  await page.getByLabel("Result status").selectOption("failed");
  await expect(page.getByRole("heading", { name: "No matching patients" })).toBeVisible();
  expect(searches.at(-1)?.searchParams.get("status")).toBe("failed");
  await page.getByRole("button", { name: "Filters 1", exact: true }).click();
  await expect(page.getByLabel("Result status")).toHaveCount(0);
  await page.getByRole("button", { name: "Clear search & filters", exact: true }).first().click();
  await expect(page.locator(".clinic-patient-row")).toHaveCount(25);
  await page.getByRole("searchbox").fill("caf");
  await expect(page.getByRole("heading", { name: "No matching patients" })).toBeVisible();
  expect(searches.at(-1)?.searchParams.get("q")).toBe("caf");
  await expect(page.getByRole("main").getByRole("link", { name: "New patient", exact: true })).toHaveCount(1);
  await page.getByRole("button", { name: "Clear search & filters", exact: true }).first().click();
  await expect(page.locator(".clinic-patient-row")).toHaveCount(25);
  for (const width of [360, 390, 545, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    await page.evaluate(() => window.scrollTo(0, 0));
    const geometry = await page.evaluate(() => {
      const row = document.querySelector(".clinic-patient-row")!.getBoundingClientRect();
      const search = document.querySelector(".search-input")!.getBoundingClientRect();
      return { overflow: document.documentElement.scrollWidth > window.innerWidth, firstRowTop: row.top, rowHeight: row.height, searchWidth: search.width };
    });
    expect(geometry.overflow).toBe(false);
    expect(geometry.firstRowTop).toBeLessThan(380);
    expect(geometry.rowHeight).toBeLessThan(width > 760 ? 85 : 115);
    expect(geometry.searchWidth).toBeGreaterThan(200);
  }
  const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(audit.violations.map(({ id }) => id)).toEqual([]);
});

test("landing renders its listening identity and packaged hero without an image optimizer", async ({ page }) => {
  await page.goto("/");
  const hero = page.getByRole("img", { name: "A blue ear with two sound waves — the iHear listening symbol" });
  await expect(hero).toBeVisible();
  expect(await hero.evaluate((image) => (image as HTMLImageElement).complete && (image as HTMLImageElement).naturalWidth > 0)).toBe(true);
  expect(await hero.getAttribute("src")).toBe("/listening-ear.webp");
  await expect(page.locator(".brand-mark")).toBeVisible();
  for (const width of [360, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  }
});
