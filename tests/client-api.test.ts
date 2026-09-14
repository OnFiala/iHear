import { test } from "node:test";
import assert from "node:assert/strict";
import { api, ApiError } from "../src/lib/client/api";

test("network failures have an actionable message without masquerading as authentication", async (t) => {
  t.mock.method(globalThis, "fetch", async () => { throw new TypeError("Failed to fetch"); });
  await assert.rejects(api("/fixture"), (error: unknown) =>
    error instanceof ApiError && error.status === 0 && error.message.includes("Check your connection"));
});

test("a successful HTML response cannot be accepted as API data", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response("<html>Reconnect</html>"));
  await assert.rejects(api("/fixture"), (error: unknown) =>
    error instanceof ApiError && error.status === 502 && error.message.includes("Reload this page"));
});

test("JSON errors retain their status and message", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ error: "A same-origin request is required." }, { status: 403 }));
  await assert.rejects(api("/fixture"), (error: unknown) =>
    error instanceof ApiError && error.status === 403 && error.message === "A same-origin request is required.");
});

test("non-JSON authentication errors retain their status", async (t) => {
  t.mock.method(globalThis, "fetch", async () => new Response("Reconnect", { status: 401 }));
  await assert.rejects(api("/fixture"), (error: unknown) => error instanceof ApiError && error.status === 401);
});

test("successful payloads and cancellation keep their original meaning", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => Response.json({ patients: [] }));
  assert.deepEqual(await api("/fixture"), { patients: [] });
  const aborted = new DOMException("Aborted", "AbortError");
  fetch.mock.mockImplementation(async () => { throw aborted; });
  await assert.rejects(api("/fixture"), (error: unknown) => error === aborted);
});
