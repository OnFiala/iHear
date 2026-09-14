import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fixture from "../fixtures/guidance-event.json";

test("directory recovers from a failed load and labels stale results honestly", async ({ page }) => {
  let fail = true;
  const patient = { ...fixture.profileSnapshot, id: fixture.patientId, displayName: "Alexandra Montgomery — synthetic design fixture", eventCount: 2, latestStatus: "ready" };
  const origin = new URL(process.env.E2E_BASE_URL || "http://localhost:3000").origin;
  await page.route("**/*", (route) => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/session") return route.fulfill({ json: { workspaceId: "explicit-ui-fixture", patient: null } });
    if (path === "/api/patients") return fail ? route.abort() : route.fulfill({ json: { patients: [patient] } });
    return route.abort();
  });
  await page.goto("/clinic");
  await expect(page.getByRole("main").getByRole("alert")).toContainText("Check your connection");
  await expect(page.getByText("No patients yet", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Updates automatically", { exact: true })).toHaveCount(0);
  fail = false;
  await page.getByRole("button", { name: "Try again", exact: true }).click();
  await expect(page.locator(".clinic-patient-name strong")).toHaveText(patient.displayName);
  await expect(page.getByRole("main").getByRole("alert")).toHaveCount(0);
  for (const width of [390, 513, 768, 1280]) {
    await page.setViewportSize({ width, height: 844 });
    const geometry = await page.evaluate(() => {
      const bounds = (selector: string) => document.querySelector(selector)!.getBoundingClientRect();
      const row = bounds(".clinic-patient-row"), avatar = bounds(".clinic-patient-identity .avatar"), name = bounds(".clinic-patient-name strong"), ears = bounds(".clinic-patient-name small");
      const search = bounds(".search-input input"), icon = bounds(".search-input svg");
      return { overflow: document.documentElement.scrollWidth > window.innerWidth, nameInside: name.right <= row.right, avatarSeparated: avatar.right < name.left, metadataSeparated: name.bottom <= ears.top, searchCentered: Math.abs((icon.top + icon.bottom - search.top - search.bottom) / 2) < 1 };
    });
    expect(geometry).toEqual({ overflow: false, nameInside: true, avatarSeparated: true, metadataSeparated: true, searchCentered: true });
  }
  const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
  expect(audit.violations.map(({ id }) => id)).toEqual([]);
  fail = true;
  await page.getByRole("searchbox").fill("new filter");
  await expect(page.getByText("Showing last loaded results", { exact: true })).toBeVisible();
  await expect(page.locator(".clinic-patient-name strong")).toHaveText(patient.displayName);
});

test("Allure confirmations align and preserve their short functional labels", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/clinic/patients/new");
  await page.getByRole("textbox", { name: "Allure app version" }).fill("explicit-fixture");
  await expect(page.getByRole("checkbox", { name: "Equalizer Bass, middle and treble controls" })).toBeVisible();
  const boxes = await page.locator(".allure-control-option").evaluateAll((elements) => elements.map((element) => ({ top: element.getBoundingClientRect().top, height: element.getBoundingClientRect().height })));
  expect(boxes).toHaveLength(3);
  expect(Math.max(...boxes.map(({ top }) => top)) - Math.min(...boxes.map(({ top }) => top))).toBeLessThan(1);
  expect(Math.max(...boxes.map(({ height }) => height))).toBeLessThan(150);
  const checkboxHeights = await page.locator(".allure-control-option input").evaluateAll((elements) => elements.map((element) => element.getBoundingClientRect().height));
  expect(checkboxHeights).toEqual([21, 21, 21]);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("paired patient sees both actions before installation help and can reopen that help", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/session") return route.fulfill({ json: { patient: { ...fixture.profileSnapshot, id: fixture.patientId } } });
    if (path === "/api/events") return route.fulfill({ json: { events: [] } });
    return route.abort();
  });
  await page.goto("/app");
  await expect(page.getByRole("button", { name: "I don’t understand", exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Keep iHear on this phone" })).toBeVisible();
  const layout = await page.evaluate(() => {
    const action = document.querySelector(".difficult-action")!.getBoundingClientRect();
    const nav = document.querySelector(".patient-bottom-nav")!.getBoundingClientRect();
    const offer = document.querySelector(".patient-install")!.getBoundingClientRect();
    return { aboveNav: action.bottom <= nav.top, beforeOffer: action.bottom <= offer.top };
  });
  expect(layout).toEqual({ aboveNav: true, beforeOffer: true });
  await page.getByRole("button", { name: "How to add" }).click();
  await expect(page.getByText("Open your browser menu.")).toBeVisible();
  await expect(page.getByText("A Home Screen copy may use separate browser storage.", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Dismiss Home Screen suggestion" }).click();
  await expect(page.getByRole("region", { name: "Home Screen access" })).toHaveCount(0);
  await page.getByRole("button", { name: "About & privacy" }).click();
  await page.getByRole("button", { name: "Home Screen access", exact: true }).click();
  await expect(page.getByText("Open your browser menu.")).toBeVisible();
});
