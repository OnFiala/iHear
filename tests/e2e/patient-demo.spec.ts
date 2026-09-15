import { test, expect } from "@playwright/test";
import path from "node:path";
import AxeBuilder from "@axe-core/playwright";

test("patient demo reaches real recording, analysis and clinician review without QR", async ({ browser }) => {
  // The ordinary browser fixture is not used for capture: this context belongs
  // to a separate fake-device browser, never the operator's physical microphone.
  const { chromium } = await import("@playwright/test");
  const fakeBrowser = await chromium.launch({ args: [
    "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
    `--use-file-for-fake-audio-capture=${path.resolve(".local/fixtures/tone-1000hz.wav")}`,
  ] });
  const baseURL = process.env.E2E_BASE_URL || "http://localhost:3000";
  const context = await fakeBrowser.newContext({ baseURL, viewport: { width: 390, height: 844 }, permissions: ["microphone"] });
  try {
    const page = await context.newPage();
    await page.goto("/app");
    await expect(page.getByRole("heading", { name: "Your listening space" })).toBeVisible();
    await expect(page.getByRole("link", { name: "Back to home" })).toHaveAttribute("href", "/");
    await expect(page.getByRole("link", { name: "Pair with clinician" })).toHaveAttribute("href", "/app/pair");
    const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
    expect(audit.violations).toEqual([]);
    await page.getByRole("link", { name: "Pair with clinician" }).click();
    await page.getByRole("link", { name: "Back to patient app" }).click();
    await page.getByRole("button", { name: "Try patient demo" }).click();
    await expect(page.getByRole("heading", { name: "Open this profile?" })).toBeVisible();
    await expect(page.getByText("Alex — demo patient", { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "Confirm profile" })).toBeDisabled();
    await page.getByRole("checkbox").check();
    await page.getByRole("button", { name: "Confirm profile" }).click();
    await expect(page.getByRole("button", { name: "Enable microphone", exact: true })).toBeVisible();
    await expect(page.getByText("Demo profile · Example audiogram and hearing aids")).toBeVisible();
    const clinician = page.getByRole("link", { name: "Open clinician view" });
    await expect(clinician).toBeVisible();
    const clinicPath = (await clinician.getAttribute("href"))!;
    const patientId = clinicPath.split("/").pop()!;
    const outsider = await browser.newContext({ baseURL });
    try {
      await outsider.request.get("/api/session");
      expect((await outsider.request.get(`/api/patients/${patientId}`)).status()).toBe(404);
      expect((await outsider.request.post(`/api/patients/${patientId}/pairing`, { headers: { Origin: baseURL }, data: {} })).status()).toBe(404);
    } finally { await outsider.close(); }
    await page.getByRole("button", { name: "Enable microphone", exact: true }).click();
    await expect(page.getByRole("button", { name: "I understand", exact: true })).toBeEnabled();
    await page.getByRole("button", { name: "I understand", exact: true }).click();
    await expect.poll(async () => {
      const result = await context.request.get("/api/events");
      return (await result.json()).events?.[0]?.status;
    }, { timeout: 90000 }).toBe("ready");
    const { events } = await (await context.request.get("/api/events")).json();
    expect(events).toHaveLength(1);
    expect(events[0].patientId).toBe(patientId);
    expect(events[0].analysis.sample_rate).toBeGreaterThanOrEqual(44100);
    expect(events[0].analysis.spectral_centroid_hz).toBeGreaterThan(900);
    expect(events[0].analysis.spectral_centroid_hz).toBeLessThan(1100);
    expect(events[0].interpretation.status).toBe("unavailable");
    await page.getByRole("button", { name: "History", exact: true }).click();
    await expect(page.getByRole("link").filter({ hasText: "I understand" })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("button", { name: "Try patient demo" })).toHaveCount(0);
    await page.getByRole("link", { name: "Open clinician view" }).click();
    await expect(page).toHaveURL(new URL(clinicPath, baseURL).href);
    await expect(page.getByRole("heading", { name: "Alex — demo patient" })).toBeVisible();
    await expect(page.getByText("Recording evidence", { exact: true })).toBeVisible();
  } finally { await fakeBrowser.close(); }
});

for (const failure of ["pairing", "uncertain-creation"] as const) {
  test(`demo entry handles ${failure} without duplicate profile creation`, async ({ page }) => {
    let creates = 0, pairs = 0;
    let profile: Record<string, unknown> | null = null;
    const id = "f93b34b1-4fd9-478d-aecc-9d05ff6fbb70";
    const origin = new URL(process.env.E2E_BASE_URL || "http://localhost:3000").origin;
    await page.route("**/*", route => new URL(route.request().url()).origin === origin ? route.continue() : route.abort());
    await page.route("**/api/**", async route => {
      const url = new URL(route.request().url());
      if (url.pathname === "/api/session") return route.fulfill({ json: { patient: null, workspaceId: "explicit-ui-fixture" } });
      if (url.pathname === "/api/patients") {
        creates++;
        if (failure === "uncertain-creation") return route.abort();
        profile = { ...route.request().postDataJSON(), id };
        return route.fulfill({ status: 201, json: { patient: profile } });
      }
      if (url.pathname === `/api/patients/${id}`) return route.fulfill({ json: { patient: profile } });
      if (url.pathname === `/api/patients/${id}/pairing`) {
        pairs++;
        return pairs === 1 ? route.fulfill({ status: 503, json: { error: "Explicit pairing failure" } })
          : route.fulfill({ json: { pairing: { code: "EXAMPLEPAIRCODE123456", url: "https://untrusted.invalid/", expiresAt: "2026-09-16T00:00:00Z" } } });
      }
      if (url.pathname === "/api/pair/EXAMPLEPAIRCODE123456") return route.fulfill({ json: { displayName: "Alex — demo patient" } });
      return route.abort();
    });
    await page.goto("/app");
    await page.getByRole("button", { name: "Try patient demo" }).click();
    if (failure === "pairing")
      await expect(page.getByRole("region", { name: "Just trying iHear?" }).getByRole("alert")).toContainText("Explicit pairing failure");
    else
      await expect(page.getByRole("status")).toContainText("may have been saved");
    await page.reload();
    if (failure === "pairing") {
      await page.getByRole("button", { name: "Continue to demo" }).click();
      await expect(page).toHaveURL(`${origin}/pair/EXAMPLEPAIRCODE123456`);
      await expect(page.getByRole("link", { name: "Back to patient app" })).toBeVisible();
      expect(pairs).toBe(2);
    } else {
      await expect(page.getByRole("button", { name: "Try patient demo" })).toBeDisabled();
      await expect(page.getByRole("status")).toContainText("may have been saved");
      expect(pairs).toBe(0);
    }
    expect(creates).toBe(1);
  });
}
