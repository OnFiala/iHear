import { test, expect, chromium, webkit } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const base = process.env.E2E_BASE_URL || "http://localhost:3000";
test("English public routes pass automated WCAG checks and keyboard navigation", async () => {
  const browser = await chromium.launch({ channel: "chrome" });
  try {
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      reducedMotion: "reduce",
    });
    const page = await context.newPage();
    for (const route of [
      "/",
      "/clinic",
      "/clinic/patients/new",
      "/app",
      "/app/pair",
    ]) {
      await page.goto(base + route, { waitUntil: "networkidle" });
      expect(await page.locator("html").getAttribute("lang")).toBe("en");
      const audit = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
        .analyze();
      expect
        .soft(
          audit.violations.map((v) => ({
            id: v.id,
            impact: v.impact,
            nodes: v.nodes.map((n) => n.target),
          })),
          route,
        )
        .toEqual([]);
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth + 1,
        ),
        route,
      ).toBe(true);
    }
    await page.goto(base + "/app/pair");
    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toHaveText("Skip to content");
    await page.keyboard.press("Enter");
    await expect(page.locator("main")).toBeFocused();
    await page.getByLabel("Pairing code", { exact: true }).focus();
    await page.keyboard.type("INVALIDCODEEXAMPLE");
    await page.keyboard.press("Tab");
    await expect(page.getByRole("button", { name: "Continue" })).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(
      page.getByRole("heading", {
        name: "This link cannot connect a profile.",
      }),
    ).toBeVisible();
  } finally {
    await browser.close();
  }
});

test("WebKit mobile layout and reduced motion render without horizontal overflow", async () => {
  const browser = await webkit.launch();
  try {
    const page = await browser.newPage({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
      reducedMotion: "reduce",
    });
    for (const route of [
      "/",
      "/clinic",
      "/clinic/patients/new",
      "/app",
      "/app/pair",
    ]) {
      await page.goto(base + route, { waitUntil: "networkidle" });
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth + 1,
        ),
        route,
      ).toBe(true);
    }
    await page.screenshot({
      path: "artifacts/webkit-pairing-mobile.png",
      fullPage: true,
    });
  } finally {
    await browser.close();
  }
});
