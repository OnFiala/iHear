import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { inspectWav, eventFingerprint } from "../src/lib/server/wav";
import {
  parseEventMetadata,
  parsePatientFilters,
  parseProfile,
  parseUuid,
} from "../src/lib/server/validation";
import { NextResponse } from "next/server";
import {
  requireSameOrigin,
  setSessionCookie,
} from "../src/lib/server/security";
import { OWNER_COOKIE, PATIENT_COOKIE } from "../src/lib/server/constants";
import { readBoundedBody } from "../src/lib/server/http";

function wav(
  sampleRate = 16_000,
  samples = 16_000,
  options: { channels?: number; bits?: number; format?: number } = {},
): Buffer {
  const channels = options.channels ?? 1;
  const bits = options.bits ?? 16;
  const format = options.format ?? 1;
  const blockAlign = (channels * bits) / 8;
  const dataBytes = samples * blockAlign;
  const bytes = Buffer.alloc(44 + dataBytes);
  bytes.write("RIFF", 0);
  bytes.writeUInt32LE(bytes.length - 8, 4);
  bytes.write("WAVE", 8);
  bytes.write("fmt ", 12);
  bytes.writeUInt32LE(16, 16);
  bytes.writeUInt16LE(format, 20);
  bytes.writeUInt16LE(channels, 22);
  bytes.writeUInt32LE(sampleRate, 24);
  bytes.writeUInt32LE(sampleRate * blockAlign, 28);
  bytes.writeUInt16LE(blockAlign, 32);
  bytes.writeUInt16LE(bits, 34);
  bytes.write("data", 36);
  bytes.writeUInt32LE(dataBytes, 40);
  return bytes;
}

test("WAV inspection accepts bounded PCM16 mono and derives duration and digest", () => {
  const bytes = wav();
  const result = inspectWav(bytes);
  assert.equal(result.sampleRate, 16_000);
  assert.equal(result.durationSeconds, 1);
  assert.deepEqual(result.sha256, createHash("sha256").update(bytes).digest());
});

test("WAV inspection rejects channel, encoding, truncation, and duration violations", () => {
  assert.throws(
    () => inspectWav(wav(16_000, 1_000, { channels: 2 })),
    /mono 16-bit PCM/,
  );
  assert.throws(
    () => inspectWav(wav(16_000, 1_000, { format: 3 })),
    /mono 16-bit PCM/,
  );
  const truncated = wav();
  truncated.writeUInt32LE(truncated.length + 100, 4);
  assert.throws(() => inspectWav(truncated), /length does not match/);
  assert.throws(
    () => inspectWav(wav(16_000, 16_000 * 11)),
    /10 seconds or shorter/,
  );
});

test("event fingerprints are stable across JSON key order and bind audio bytes", () => {
  const audioA = createHash("sha256").update("a").digest();
  const audioB = createHash("sha256").update("b").digest();
  assert.deepEqual(
    eventFingerprint({ b: 2, a: { y: 2, x: 1 } }, audioA),
    eventFingerprint({ a: { x: 1, y: 2 }, b: 2 }, audioA),
  );
  assert.notDeepEqual(
    eventFingerprint({ a: 1 }, audioA),
    eventFingerprint({ a: 1 }, audioB),
  );
});

const validProfile = {
  displayName: "Alex Example",
  audiogram: { frequencies: [250, 500], left: [20, 25], right: [15, 30] },
  aids: {
    side: "bilateral" as const,
    left: { model: "Example", tier: "110" },
    right: { model: "Example", tier: "110" },
  },
  followUpDate: "2026-09-20",
  note: "",
  timezone: "Europe/Prague",
};

test("profile validation preserves the shared shape and rejects inconsistent arrays/devices", () => {
  assert.deepEqual(parseProfile(validProfile), validProfile);
  assert.throws(
    () =>
      parseProfile({
        ...validProfile,
        audiogram: { ...validProfile.audiogram, right: [10] },
      }),
    /matching lengths/,
  );
  assert.throws(
    () =>
      parseProfile({
        ...validProfile,
        aids: { ...validProfile.aids, right: null },
      }),
    /requires both devices/,
  );
  assert.throws(
    () => parseProfile({ ...validProfile, timezone: "not/a-zone" }),
    /Timezone is invalid/,
  );
  assert.throws(
    () => parseProfile({ ...validProfile, followUpDate: "2026-02-31" }),
    /Follow-up date is invalid/,
  );
});

test("identifier and search filters reject malformed values before SQL", () => {
  assert.throws(
    () => parseUuid("not-a-uuid", "Patient ID"),
    /Patient ID is invalid/,
  );
  assert.throws(
    () => parsePatientFilters(new URLSearchParams({ status: "unknown" })),
    /Status filter is invalid/,
  );
  assert.throws(
    () => parsePatientFilters(new URLSearchParams({ followUp: "2026-02-31" })),
    /Follow-up filter is invalid/,
  );
  assert.deepEqual(
    parsePatientFilters(
      new URLSearchParams({ q: " Alex ", followUp: "upcoming" }),
    ),
    {
      q: "Alex",
      status: undefined,
      difficulty: undefined,
      followUp: "upcoming",
    },
  );
});

const validMetadata = {
  id: "11111111-1111-4111-8111-111111111111",
  patientId: "22222222-2222-4222-8222-222222222222",
  kind: "difficult" as const,
  difficulty: "Several people talking",
  environment: "Background conversation",
  capturedAt: "2026-09-11T12:00:00.000Z",
  capture: {
    sampleRate: 16_000,
    preSeconds: 5,
    postSeconds: 5,
    trackSettings: {},
    sourceLabel: "Phone microphone",
    routing: "unknown" as const,
    interrupted: false,
  },
};

test("event validation requires negative answers and forbids them on understood events", () => {
  assert.deepEqual(parseEventMetadata(validMetadata), validMetadata);
  assert.throws(
    () => parseEventMetadata({ ...validMetadata, difficulty: null }),
    /required for a difficult event/,
  );
  assert.throws(
    () => parseEventMetadata({ ...validMetadata, kind: "understood" }),
    /cannot include difficulty answers/,
  );
  assert.doesNotThrow(() =>
    parseEventMetadata({
      ...validMetadata,
      kind: "understood",
      difficulty: null,
      environment: null,
    }),
  );
});

test("CSRF validation uses configured origins and ignores a forged forwarded host", () => {
  const previousOrigin = process.env.APP_PUBLIC_ORIGIN;
  const previousDevelopment = process.env.DEV_ALLOWED_ORIGINS;
  process.env.APP_PUBLIC_ORIGIN = "https://trusted.example";
  process.env.DEV_ALLOWED_ORIGINS = "http://localhost:3000";
  const request = (origin: string, forwardedHost = "attacker.example") =>
    ({
      headers: new Headers({ origin, "x-forwarded-host": forwardedHost }),
      nextUrl: new URL("http://internal:3000/api/patients"),
    }) as never;
  try {
    assert.doesNotThrow(() =>
      requireSameOrigin(request("https://trusted.example")),
    );
    assert.doesNotThrow(() =>
      requireSameOrigin(request("http://localhost:3000")),
    );
    assert.throws(
      () => requireSameOrigin(request("https://attacker.example")),
      /same-origin/,
    );
  } finally {
    if (previousOrigin === undefined) delete process.env.APP_PUBLIC_ORIGIN;
    else process.env.APP_PUBLIC_ORIGIN = previousOrigin;
    if (previousDevelopment === undefined)
      delete process.env.DEV_ALLOWED_ORIGINS;
    else process.env.DEV_ALLOWED_ORIGINS = previousDevelopment;
  }
});

test("owner and patient capabilities coexist in separate scoped HttpOnly cookies", () => {
  const response = NextResponse.json({ ok: true });
  const request = {
    headers: new Headers({ "x-forwarded-proto": "https" }),
    nextUrl: new URL("http://internal/api/session"),
  } as never;
  setSessionCookie(response, request, "owner", "owner-token");
  setSessionCookie(
    response,
    request,
    "patient",
    "patient-token",
    new Date("2026-10-01T00:00:00Z"),
  );
  const cookies = response.cookies.getAll();
  assert.deepEqual(
    cookies.map((cookie) => cookie.name).sort(),
    [OWNER_COOKIE, PATIENT_COOKIE].sort(),
  );
  const header = response.headers.get("set-cookie") ?? "";
  assert.match(header, /HttpOnly/);
  assert.match(header, /SameSite=lax/i);
  assert.match(header, /Secure/);
});

test("bounded request reading enforces actual streamed bytes despite a false Content-Length", async () => {
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new Uint8Array(6));
      controller.enqueue(new Uint8Array(6));
      controller.close();
    },
  });
  const request = new Request("http://localhost/upload", {
    method: "POST",
    headers: { "content-length": "3" },
    body: stream,
    duplex: "half",
  } as RequestInit);
  await assert.rejects(
    readBoundedBody(request, 10),
    /request body is too large/,
  );
  await assert.rejects(
    readBoundedBody(
      new Request("http://localhost/upload", {
        method: "POST",
        headers: { "content-length": "11" },
        body: "x",
      }),
      10,
    ),
    /request body is too large/,
  );
});
