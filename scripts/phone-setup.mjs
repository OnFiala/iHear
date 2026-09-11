import { chromium } from "@playwright/test";
import { writeFile, mkdir, chmod } from "node:fs/promises";
const origin = process.env.E2E_BASE_URL;
if (!origin)
  throw new Error(
    "Set E2E_BASE_URL to the reachable HTTPS development origin.",
  );
const browser = await chromium.launch({ channel: "chrome", headless: true });
const context = await browser.newContext({
  baseURL: origin,
  viewport: { width: 1440, height: 1000 },
});
const page = await context.newPage();
try {
  await page.goto("/clinic");
  await page.getByRole("link", { name: "Create demo patient" }).first().click();
  await page.getByLabel("Display name").fill("Alex Rivers");
  await page
    .getByLabel("Brief demo note")
    .fill("Synthetic profile for a controlled phone-microphone test.");
  await page.getByRole("button", { name: "Create demo profile" }).click();
  await page.waitForURL(/\/clinic\/patients\/[a-f0-9-]+$/, { timeout: 15000 });
  const patientId = page.url().split("/").pop();
  await page.getByRole("button", { name: "Create pairing QR" }).click();
  await page.getByRole("link", { name: "Open pairing link" }).waitFor();
  const pairingURL = await page
    .getByRole("link", { name: "Open pairing link" })
    .getAttribute("href");
  const code = await page.getByTestId("pairing-code").innerText();
  await mkdir(".local", { recursive: true });
  await context.storageState({ path: ".local/phone-demo-owner.json" });
  await chmod(".local/phone-demo-owner.json", 0o600);
  await writeFile(
    ".local/phone-demo.json",
    JSON.stringify({ patientId, pairingURL, code }, null, 2),
    { mode: 0o600 },
  );
  await page.screenshot({
    path: "artifacts/phone-demo-clinician.png",
    fullPage: true,
  });
  console.log(JSON.stringify({ patientId, pairingURL, code }));
} catch (error) {
  await page.screenshot({
    path: "artifacts/phone-setup-error.png",
    fullPage: true,
  });
  console.error(await page.locator("body").innerText());
  throw error;
} finally {
  await browser.close();
}
