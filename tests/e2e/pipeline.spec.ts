import {
  test,
  expect,
  chromium,
  type BrowserContext,
  type Page,
} from "@playwright/test";
import path from "node:path";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { randomUUID } from "node:crypto";
import QRCode from "qrcode";
import AxeBuilder from "@axe-core/playwright";
test.describe.configure({ mode: "serial" });
const base = process.env.E2E_BASE_URL || "http://localhost:3000";
let browser: Awaited<ReturnType<typeof chromium.launch>>;
let owner: BrowserContext, phone: BrowserContext, stranger: BrowserContext;
let patientId: string, pairURL: string, eventId: string;
const name = `Demo Robin ${Date.now()}`;
async function open(page: Page, url: string) {
  await page.goto(url, { waitUntil: "networkidle" });
}
async function noHorizontalOverflow(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);
}

test.beforeAll(async () => {
  browser = await chromium.launch({
    channel: "chrome",
    headless: true,
    args: [
      "--use-fake-ui-for-media-stream",
      "--use-fake-device-for-media-stream",
      `--use-file-for-fake-audio-capture=${path.resolve(".local/fixtures/tone-1000hz.wav")}`,
    ],
  });
  owner = await browser.newContext({
    baseURL: base,
    viewport: { width: 1440, height: 1000 },
  });
  phone = await browser.newContext({
    baseURL: base,
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    permissions: ["microphone", "camera"],
  });
  stranger = await browser.newContext({ baseURL: base });
});
test.afterAll(async () => {
  await browser?.close();
});

test("clinician creates synthetic profile and the QR pairing confirms the same patient", async () => {
  const p = await owner.newPage();
  await open(p, base + "/clinic");
  await p.getByRole("link", { name: "Create demo patient" }).first().click();
  await p.getByLabel("Display name").fill(name);
  await p
    .getByLabel("Brief demo note")
    .fill("Synthetic garden conversation for full-text search.");
  await p.getByRole("button", { name: "Create demo profile" }).click();
  await expect(p).toHaveURL(/\/clinic\/patients\/[a-f0-9-]+$/);
  patientId = p.url().split("/").pop()!;
  await expect(p.getByRole("heading", { name, exact: true })).toBeVisible();
  await p.getByRole("button", { name: "Create pairing QR" }).click();
  const link = p.getByRole("link", { name: "Open pairing link" });
  await expect(link).toBeVisible();
  pairURL = (await link.getAttribute("href"))!;
  const qr = p.getByRole("img", {
    name: "QR code for this demo profile’s opaque pairing link",
  });
  await expect(qr).toBeVisible();
  expect(pairURL).not.toContain(encodeURIComponent(name));
  await p.screenshot({
    path: "artifacts/clinician-desktop.png",
    fullPage: true,
  });
  await noHorizontalOverflow(p);
  const app = await phone.newPage();
  await open(app, pairURL);
  await expect(app.getByText(name, { exact: true })).toBeVisible();
  await app.getByRole("checkbox").check();
  await app
    .getByRole("button", { name: "Yes, open my listening space" })
    .click();
  await expect(
    app.getByRole("heading", { name: "Hello, Demo." }),
  ).toBeVisible();
  await app.reload();
  await expect(
    app.getByRole("heading", { name: "Hello, Demo." }),
  ).toBeVisible();
  await noHorizontalOverflow(app);
  await app.screenshot({
    path: "artifacts/patient-mobile.png",
    fullPage: true,
  });
});

test("both actions save real fake-device PCM; negative answers and DSP reach correct clinician profile", async () => {
  const p = phone.pages()[0];
  await p.getByRole("button", { name: "Enable microphone" }).click();
  await expect(p.getByText("Microphone ready", { exact: true })).toBeVisible();
  const accessibility = await new AxeBuilder({ page: p })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(
    accessibility.violations.map((v) => ({
      id: v.id,
      targets: v.nodes.map((n) => n.target),
    })),
  ).toEqual([]);
  await p.waitForTimeout(5300);
  await p
    .getByRole("button", { name: "I understand", exact: false })
    .first()
    .click();
  await expect(
    p.getByText(
      "Moment received. Your clinician will see it after processing.",
    ),
  ).toBeVisible({ timeout: 30000 });
  await p
    .getByRole("button", { name: "I don’t understand", exact: false })
    .click();
  await expect(
    p.getByRole("heading", { name: "What was difficult?" }),
  ).toBeVisible({ timeout: 25000 });
  await p.getByLabel("Several people talking", { exact: true }).check();
  await p.getByLabel("Background conversation", { exact: true }).check();
  await p.getByRole("button", { name: "Save these answers" }).click();
  await expect(
    p.getByText("Moment received. Thank you for sharing what happened."),
  ).toBeVisible({ timeout: 30000 });
  const response = await phone.request.get("/api/events");
  expect(response.ok()).toBe(true);
  const rows = (await response.json()).events;
  expect(rows).toHaveLength(2);
  const negative = rows.find((e: any) => e.kind === "difficult");
  eventId = negative.id;
  expect(negative.difficulty).toBe("Several people talking");
  expect(negative.environment).toBe("Background conversation");
  expect(negative.profileSnapshot.displayName).toBe(name);
  expect(negative.capture.preSeconds).toBeCloseTo(5, 1);
  expect(negative.capture.postSeconds).toBeCloseTo(5, 1);
  await expect
    .poll(
      async () => {
        const r = await phone.request.get("/api/events/" + eventId);
        return (await r.json()).event.status;
      },
      { timeout: 180000, intervals: [2000] },
    )
    .toBe("ready");
  const detail = (
    await (await phone.request.get("/api/events/" + eventId)).json()
  ).event;
  expect(detail.analysis.sample_rate).toBe(48000);
  expect(detail.analysis.duration_seconds).toBeCloseTo(10, 1);
  expect(detail.analysis.spectral_centroid_hz).toBeGreaterThan(900);
  expect(detail.analysis.spectral_centroid_hz).toBeLessThan(1100);
  expect(detail.interpretation.status).toBe("unavailable");
  const clinic = owner.pages()[0];
  await clinic.reload();
  await expect(
    clinic.getByText("Relative spectral energy").first(),
  ).toBeVisible();
  await clinic.screenshot({
    path: "artifacts/clinician-results.png",
    fullPage: true,
  });
});

test("database full-text search finds profile notes and negative event content", async () => {
  const p = owner.pages()[0];
  await open(p, base + "/clinic");
  await p.getByRole("searchbox").fill("garden");
  await expect(p.getByRole("heading", { name, exact: true })).toBeVisible();
  await p.getByRole("searchbox").fill("Several people talking");
  await expect(p.getByRole("heading", { name, exact: true })).toBeVisible();
  await p.getByRole("searchbox").fill("doesnotexistword");
  await expect(
    p.getByRole("heading", { name: "No matching profiles" }),
  ).toBeVisible();
});

test("other visitors and patient-only capabilities cannot read or mutate clinician data", async () => {
  await stranger.request.get("/api/session");
  let r = await stranger.request.get("/api/patients/" + patientId);
  expect([401, 403, 404]).toContain(r.status());
  r = await stranger.request.get("/api/events/" + eventId);
  expect([401, 403, 404]).toContain(r.status());
  r = await stranger.request.post("/api/patients/" + patientId + "/pairing", {
    headers: { Origin: base },
    data: {},
  });
  expect([401, 403, 404]).toContain(r.status());
  r = await phone.request.get("/api/patients");
  expect(r.status()).toBe(401);
  r = await phone.request.patch("/api/patients/" + patientId, {
    headers: { Origin: base },
    data: { displayName: "Unauthorized" },
  });
  expect([401, 403, 404]).toContain(r.status());
  r = await owner.request.post("/api/patients/" + patientId + "/pairing", {
    headers: { Origin: "https://untrusted.example" },
    data: {},
  });
  expect(r.status()).toBe(403);
});

test("offline capture survives reopening and foreground retry without duplicate events", async () => {
  const p = phone.pages()[0];
  await open(p, base + "/app");
  await p.getByRole("button", { name: "Enable microphone" }).click();
  await expect(p.getByText("Microphone ready", { exact: true })).toBeVisible();
  await p.waitForTimeout(1200);
  await phone.setOffline(true);
  await p
    .getByRole("button", { name: "I understand", exact: false })
    .first()
    .click();
  await expect(
    p.getByText("Moment saved on this device. Thank you."),
  ).toBeVisible({ timeout: 25000 });
  await expect(
    p.getByText("saved locally", { exact: false }).first(),
  ).toBeVisible();
  await p.reload({ waitUntil: "domcontentloaded" });
  await expect(p.getByRole("heading", { name: "Hello, Demo." })).toBeVisible({
    timeout: 20000,
  });
  await expect(
    p.getByText("saved locally", { exact: false }).first(),
  ).toBeVisible();
  await phone.setOffline(false);
  await expect
    .poll(
      async () => {
        const r = await phone.request.get("/api/events");
        return (await r.json()).events.length;
      },
      { timeout: 30000 },
    )
    .toBe(3);
  await p.reload();
  await expect
    .poll(async () => {
      const r = await phone.request.get("/api/events");
      return (await r.json()).events.length;
    })
    .toBe(3);
});

test("on-demand report is a real PDF and repeated requests reuse its revision", async () => {
  // Wait for the newly uploaded offline moment to finish before requesting a stable report revision.
  await expect
    .poll(
      async () => {
        const r = await phone.request.get("/api/events");
        return (await r.json()).events.every(
          (event: { status: string }) => event.status === "ready",
        );
      },
      { timeout: 60000 },
    )
    .toBe(true);
  const p = owner.pages()[0];
  await open(p, base + "/clinic/patients/" + patientId);
  await p.getByRole("button", { name: "Prepare PDF report" }).click();
  await expect(
    p.getByRole("link", { name: "Download PDF report" }),
  ).toBeVisible({ timeout: 120000 });
  const url = (await p
    .getByRole("link", { name: "Download PDF report" })
    .getAttribute("href"))!;
  const r = await owner.request.get(url);
  expect(r.status()).toBe(200);
  expect(r.headers()["content-type"]).toContain("application/pdf");
  const bytes = await r.body();
  expect(bytes.subarray(0, 5).toString()).toBe("%PDF-");
  expect(bytes.length).toBeGreaterThan(1500);
  const { writeFile } = await import("node:fs/promises");
  await writeFile("artifacts/report.pdf", bytes);
  const a = await owner.request.post("/api/patients/" + patientId + "/report", {
      headers: { Origin: base },
      data: {},
    }),
    b = await owner.request.post("/api/patients/" + patientId + "/report", {
      headers: { Origin: base },
      data: {},
    });
  const firstReport = await a.json();
  const secondReport = await b.json();
  expect(firstReport.reportId).toMatch(/^[a-f0-9-]{36}$/);
  expect(firstReport.reportId).toBe(secondReport.reportId);
});

test("identical concurrent uploads reuse one event and one analysis", async () => {
  const id = randomUUID();
  const audio = await readFile(".local/fixtures/tone-1000hz.wav");
  // The fixture file is longer for Chrome looping; this upload uses an exact 10-second PCM segment.
  const wav = Buffer.from(audio.subarray(0, 44 + 48000 * 10 * 2));
  wav.writeUInt32LE(wav.length - 8, 4);
  wav.writeUInt32LE(wav.length - 44, 40);
  const metadata = {
    id,
    patientId,
    kind: "understood",
    difficulty: null,
    environment: null,
    capturedAt: new Date().toISOString(),
    capture: {
      sampleRate: 48000,
      preSeconds: 5,
      postSeconds: 5,
      trackSettings: { sampleRate: 48000 },
      sourceLabel: "Deterministic test source",
      routing: "unknown",
      interrupted: false,
    },
  };
  const submit = () =>
    phone.request.post("/api/events", {
      headers: { Origin: base },
      multipart: {
        metadata: JSON.stringify(metadata),
        audio: { name: "moment.wav", mimeType: "audio/wav", buffer: wav },
      },
    });
  const responses = await Promise.all([submit(), submit()]);
  expect(responses.every((r) => r.ok())).toBe(true);
  const rows = (await (await phone.request.get("/api/events")).json()).events;
  expect(rows.filter((e: any) => e.id === id)).toHaveLength(1);
  await expect
    .poll(
      async () => {
        const r = await phone.request.get("/api/events/" + id);
        return (await r.json()).event.status;
      },
      { timeout: 60000 },
    )
    .toBe("ready");
  const repeated = await submit();
  expect(repeated.ok()).toBe(true);
  expect(
    (await (await phone.request.get("/api/events")).json()).events.filter(
      (e: any) => e.id === id,
    ),
  ).toHaveLength(1);
  const changedReport = await owner.request.get(
    "/api/patients/" + patientId + "/report",
  );
  expect((await changedReport.json()).status).toBe("outdated");
  const clinic = owner.pages()[0];
  await clinic.reload();
  await expect(
    clinic.getByText(
      "New information arrived after the report was requested.",
      { exact: false },
    ),
  ).toBeVisible();
});

test("in-app QR scanner decodes a real camera fixture and revocation blocks old pairing", async () => {
  const qr = QRCode.create(pairURL, { errorCorrectionLevel: "M" }).modules;
  const width = 640,
    height = 480,
    scale = Math.floor(400 / (qr.size + 8)),
    left = Math.floor((width - qr.size * scale) / 2),
    top = Math.floor((height - qr.size * scale) / 2);
  const y = Buffer.alloc(width * height, 235),
    uv = Buffer.alloc((width * height) / 2, 128);
  for (let row = 0; row < qr.size; row++)
    for (let col = 0; col < qr.size; col++)
      if (qr.get(row, col))
        for (let dy = 0; dy < scale; dy++)
          y.fill(
            16,
            (top + row * scale + dy) * width + left + col * scale,
            (top + row * scale + dy) * width + left + (col + 1) * scale,
          );
  await mkdir(".local/fixtures", { recursive: true });
  const videoPath = path.resolve(".local/fixtures/pairing-camera.y4m");
  await writeFile(
    videoPath,
    Buffer.concat([
      Buffer.from(
        `YUV4MPEG2 W${width} H${height} F30:1 Ip A1:1 C420jpeg\nFRAME\n`,
      ),
      y,
      uv,
    ]),
  );
  const cameraBrowser = await chromium.launch({
    channel: "chrome",
    args: [
      "--use-fake-ui-for-media-stream",
      "--use-fake-device-for-media-stream",
      `--use-file-for-fake-video-capture=${videoPath}`,
    ],
  });
  try {
    const context = await cameraBrowser.newContext({
      baseURL: base,
      permissions: ["camera"],
    });
    const p = await context.newPage();
    await p.goto("/app/pair");
    await p.getByRole("button", { name: "Open camera to scan" }).click();
    await expect(p).toHaveURL(pairURL, { timeout: 30000 });
    await expect(p.getByText(name, { exact: true })).toBeVisible();
    const revoked = await owner.request.delete(
      "/api/patients/" + patientId + "/pairing",
      { headers: { Origin: base } },
    );
    expect(revoked.ok()).toBe(true);
    expect((await phone.request.get("/api/events")).status()).toBe(401);
    await p.reload();
    await expect(
      p.getByRole("heading", { name: "This link cannot connect a profile." }),
    ).toBeVisible();
  } finally {
    await cameraBrowser.close();
  }
});
