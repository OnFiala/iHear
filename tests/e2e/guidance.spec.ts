import { test, expect, type Page } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import fixtureJson from "../fixtures/guidance-event.json";
import type { ListeningEvent, Patient, ProfileInput } from "../../src/lib/types";

const base = process.env.E2E_BASE_URL || "http://localhost:3000";
const fixture = fixtureJson as ListeningEvent;

function copy<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function patientFor(aids: ProfileInput["aids"] = fixture.currentAids!) {
  return {
    ...copy(fixture.profileSnapshot),
    id: fixture.patientId,
    workspaceId: "d4a2bda6-870a-43e5-94a1-5f1190bf8d7e",
    createdAt: fixture.createdAt,
    aids: copy(aids),
    eventCount: 1,
    latestStatus: "ready",
  } satisfies Patient;
}

function patientEvent(event: ListeningEvent): ListeningEvent {
  const interpretation = event.interpretation;
  return {
    ...copy(event),
    interpretation: interpretation?.result
      ? {
          ...interpretation,
          result: {
            patient_summary: interpretation.result.patient_summary,
            tip_ids: interpretation.result.tip_ids,
            device_action_ids: interpretation.result.device_action_ids,
          },
        }
      : interpretation,
  };
}

async function guardExternalAndMockApi(
  page: Page,
  event: ListeningEvent,
  currentAids: ProfileInput["aids"] = event.currentAids ?? event.profileSnapshot.aids,
  created?: (body: unknown) => void,
) {
  const baseOrigin = new URL(base).origin;
  await page.route("**/*", async (route) => {
    if (new URL(route.request().url()).origin !== baseOrigin) await route.abort();
    else await route.continue();
  });
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (path === "/api/session" && request.method() === "GET") {
      await route.fulfill({ json: { workspaceId: "fixture-workspace", patient: null } });
      return;
    }
    if (path === `/api/patients/${fixture.patientId}` && request.method() === "GET") {
      await route.fulfill({
        json: { patient: patientFor(currentAids), events: [{ ...copy(event), currentAids: copy(currentAids) }], pairing: null },
      });
      return;
    }
    if (path === `/api/patients/${fixture.patientId}/report` && request.method() === "GET") {
      await route.fulfill({ json: { status: "missing" } });
      return;
    }
    if (path === `/api/events/${fixture.id}` && request.method() === "GET") {
      await route.fulfill({
        json: { event: { ...patientEvent(event), currentAids: copy(currentAids) } },
      });
      return;
    }
    if (path === "/api/patients" && request.method() === "POST" && created) {
      created(request.postDataJSON());
      await route.fulfill({ status: 201, json: { patient: patientFor(currentAids) } });
      return;
    }
    await route.abort();
  });
}

async function expectNoHorizontalOverflow(page: Page) {
  await expect.poll(() => page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth + 1,
  )).toBe(true);
}

async function expectNoAxeViolations(page: Page) {
  const audit = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(audit.violations.map((violation) => violation.id)).toEqual([]);
}

test("explicit fixture renders clinician and patient guidance without exposing clinician text", async ({ browser }) => {
  const clinicianContext = await browser.newContext({ baseURL: base, viewport: { width: 1440, height: 1000 } });
  const clinician = await clinicianContext.newPage();
  await guardExternalAndMockApi(clinician, fixture, fixture.profileSnapshot.aids);
  await clinician.goto(`/clinic/patients/${fixture.patientId}`, { waitUntil: "networkidle" });
  await expect(clinician.getByRole("heading", { name: "Clinical review guidance" })).toBeVisible();
  await expect(clinician.getByText("2,000–4,000 Hz", { exact: true })).toBeVisible();
  await expect(clinician.getByText("Review which voices or scenes are difficult", { exact: false })).toBeVisible();
  await expect(clinician.getByText("Based on: Patient report", { exact: false })).toBeVisible();
  await expect(clinician.locator(".band--review")).toHaveCount(1);
  await clinician.screenshot({ path: ".local/guidance-acceptance/guidance-clinician-desktop.png", fullPage: true });
  await clinician.setViewportSize({ width: 390, height: 844 });
  await expectNoHorizontalOverflow(clinician);
  await expectNoAxeViolations(clinician);
  await clinicianContext.close();

  const patientContext = await browser.newContext({ baseURL: base, viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const patient = await patientContext.newPage();
  await guardExternalAndMockApi(patient, fixture, fixture.profileSnapshot.aids);
  await patient.goto(`/app/events/${fixture.id}`, { waitUntil: "networkidle" });
  await expect(patient.getByText("You reported difficulty following the television.", { exact: false })).toBeVisible();
  await expect(patient.getByText("AI listening note", { exact: true })).toBeVisible();
  await expect(patient.getByRole("heading", { name: /equalizer/i })).toBeVisible();
  await expect(patient.getByText("Patient report, audiogram thresholds", { exact: false })).toHaveCount(0);
  await expect(patient.getByText("Review which voices or scenes", { exact: false })).toHaveCount(0);
  await expectNoHorizontalOverflow(patient);
  await expectNoAxeViolations(patient);
  await patient.screenshot({ path: ".local/guidance-acceptance/guidance-patient-mobile.png", fullPage: true });
  await patientContext.close();
});

test("explicit fixture suppresses historic device cards when the current confirmation changes", async ({ browser }) => {
  const changedAids: ProfileInput["aids"] = {
    ...copy(fixture.profileSnapshot.aids),
    app: { ...fixture.profileSnapshot.aids.app!, confirmedActions: [] },
  };
  const context = await browser.newContext({ baseURL: base, viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const page = await context.newPage();
  await guardExternalAndMockApi(page, fixture, changedAids);
  await page.goto(`/app/events/${fixture.id}`, { waitUntil: "networkidle" });
  await expect(page.getByText("App configuration has changed since this moment.", { exact: false })).toBeVisible();
  await expect(page.getByRole("heading", { name: /equalizer/i })).toHaveCount(0);
  await context.close();
});

test("explicit fixture keeps an unavailable interpretation visibly unavailable", async ({ browser }) => {
  const unavailable: ListeningEvent = {
    ...copy(fixture),
    interpretation: { status: "unavailable", result: null },
  };
  const context = await browser.newContext({ baseURL: base, viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const page = await context.newPage();
  await guardExternalAndMockApi(page, unavailable, unavailable.profileSnapshot.aids);
  await page.goto(`/app/events/${fixture.id}`, { waitUntil: "networkidle" });
  await expect(page.getByText("Automated interpretation: unavailable.", { exact: false })).toBeVisible();
  await expect(page.getByRole("heading", { name: "What may help next" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: /equalizer/i })).toHaveCount(0);
  await context.close();
});

test("explicit fixture form confirmation clears on app-version and tier changes before its intercepted save", async ({ browser }) => {
  let saved: unknown;
  const context = await browser.newContext({ baseURL: base, viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  await guardExternalAndMockApi(page, fixture, fixture.profileSnapshot.aids, (body) => { saved = body; });
  await page.goto("/clinic/patients/new", { waitUntil: "networkidle" });
  const version = page.getByLabel("Allure app version", { exact: true });
  const equalizer = page.getByRole("checkbox", { name: /equalizer/i });
  await version.fill("fixture-1.0");
  await equalizer.check();
  await expect(equalizer).toBeChecked();
  await version.fill("fixture-1.1");
  await expect(equalizer).not.toBeChecked();
  await equalizer.check();
  const leftTier = page.getByRole("group", { name: "Left hearing aid" }).getByLabel("Tier");
  await leftTier.selectOption("330");
  await expect(version).toHaveValue("");
  await expect(equalizer).toHaveCount(0);
  await leftTier.selectOption("220");
  await version.fill("fixture-1.0");
  await equalizer.check();
  await page.getByRole("textbox", { name: /^Name/ }).fill("Synthetic browser fixture");
  await page.getByRole("button", { name: "Create patient" }).click();
  await expect.poll(() => saved).toBeTruthy();
  expect(saved).toMatchObject({
    aids: {
      app: {
        name: "Widex Allure",
        version: "fixture-1.0",
        confirmedActions: ["allure_equalizer"],
      },
    },
  });
  await context.close();
});
