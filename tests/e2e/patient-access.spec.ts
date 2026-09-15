import {
  expect,
  test,
  chromium,
  type Browser,
  type BrowserContext,
} from "@playwright/test";
import path from "node:path";

const base = process.env.E2E_BASE_URL || "http://localhost:3000";
let browser: Browser;
let context: BrowserContext;

test.beforeAll(async () => {
  browser = await chromium.launch({
    channel: "chrome",
    headless: true,
    args: [
      "--use-fake-ui-for-media-stream",
      "--use-fake-device-for-media-stream",
      "--use-file-for-fake-audio-capture=" +
        path.resolve(".local/fixtures/tone-1000hz.wav"),
    ],
  });
  context = await browser.newContext({
    baseURL: base,
    viewport: { width: 390, height: 844 },
    permissions: ["microphone"],
    serviceWorkers: "block",
  });
});

test.afterAll(async () => {
  await browser?.close();
});

test("remembered consent restores only while visible and follows browser revocation", async () => {
  const page = await context.newPage();
  await page.addInitScript(() => {
    class TestMicrophonePermission extends EventTarget {
      state: PermissionState = "granted";
    }
    const permission = new TestMicrophonePermission();
    Object.defineProperty(navigator, "permissions", {
      configurable: true,
      value: {
        query: async ({ name }: PermissionDescriptor) => {
          if (name !== "microphone") throw new TypeError("Unsupported permission");
          return permission;
        },
      },
    });
    Object.defineProperty(window, "__setIhearMicrophonePermission", {
      configurable: true,
      value: (state: PermissionState) => {
        permission.state = state;
        permission.dispatchEvent(new Event("change"));
      },
    });
  });
  const patient = {
    id: "11111111-1111-4111-8111-111111111111",
    workspaceId: "22222222-2222-4222-8222-222222222222",
    displayName: "Demo Listener",
    audiogram: { frequencies: [], left: [], right: [] },
    aids: { side: "bilateral", left: null, right: null },
    followUpDate: "2026-09-28",
    note: "",
    timezone: "Europe/Prague",
    createdAt: "2026-09-12T00:00:00.000Z",
  };
  await page.route("**/api/session", (route) =>
    route.fulfill({ status: 200, json: { patient } }),
  );
  await page.route("**/api/events", (route) =>
    route.fulfill({ status: 200, json: { events: [] } }),
  );

  await page.goto(base + "/app", { waitUntil: "networkidle" });
  await expect(
    page.getByRole("button", { name: "Enable microphone" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Enable microphone" }).click();
  await expect(page.getByText("Microphone on", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: /^I (understand|don’t understand)$/ }),
  ).toHaveCount(2);

  await page.reload({ waitUntil: "networkidle" });
  await expect(page.getByText("Microphone on", { exact: true })).toBeVisible();

  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "hidden",
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect(
    page.getByText("Microphone paused while iHear was in the background."),
  ).toBeVisible();
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "visible",
    });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect(page.getByText("Microphone on", { exact: true })).toBeVisible();

  await page.evaluate(() =>
    (
      window as typeof window & {
        __setIhearMicrophonePermission: (state: PermissionState) => void;
      }
    ).__setIhearMicrophonePermission("prompt"),
  );
  await expect(
    page.getByRole("button", { name: "Enable microphone" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "I understand", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "I don’t understand", exact: true }),
  ).toBeDisabled();

  await page.evaluate(() =>
    (
      window as typeof window & {
        __setIhearMicrophonePermission: (state: PermissionState) => void;
      }
    ).__setIhearMicrophonePermission("granted"),
  );
  await expect(page.getByText("Microphone on", { exact: true })).toBeVisible();
});

test("native install dismissal falls back to truthful manual instructions", async () => {
  const page = await context.newPage();
  await page.route("**/api/session", (route) =>
    route.fulfill({ status: 200, json: { patient: null } }),
  );
  await page.goto(base + "/app", { waitUntil: "networkidle" });
  await page.getByText("Keep iHear on your phone", { exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Keep iHear on this phone" }),
  ).toBeVisible();
  await page.evaluate(() => {
    const event = new Event("beforeinstallprompt", { cancelable: true });
    Object.defineProperty(event, "prompt", {
      value: async () => ({ outcome: "dismissed", platform: "" }),
    });
    window.dispatchEvent(event);
  });
  await page.getByRole("button", { name: "Add to Home Screen" }).click();
  await expect(page.getByText("Open your browser menu.")).toBeVisible();
  await expect(
    page.getByText("Choose Install app or Add to Home screen."),
  ).toBeVisible();
  await expect(page.getByText(/installed successfully/i)).toHaveCount(0);
});
