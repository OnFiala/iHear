import "server-only";
import { createHash, createHmac, randomBytes } from "node:crypto";
import type { NextRequest, NextResponse } from "next/server";
import { HttpError } from "./http";
import { OWNER_COOKIE, PATIENT_COOKIE } from "./constants";

export function randomCapability(): string {
  return randomBytes(32).toString("base64url");
}

export function hashCapability(token: string): Buffer {
  return createHash("sha256").update(token, "utf8").digest();
}

const BASE32 = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

export function randomPairingToken(length = 32): string {
  const bytes = randomBytes(length);
  let result = "";
  for (let index = 0; index < length; index += 1)
    result += BASE32[bytes[index] % BASE32.length];
  return result;
}

export function normalizePairingToken(token: string): string {
  const normalized = token.toUpperCase().replace(/[^A-Z2-9]/g, "");
  if (
    normalized.length !== 32 ||
    [...normalized].some((character) => !BASE32.includes(character))
  ) {
    throw new HttpError(404, "This pairing code is invalid or has expired.");
  }
  return normalized;
}

export function displayPairingToken(token: string): string {
  return token.match(/.{1,4}/g)?.join("-") ?? token;
}

function allowedOrigins(request: NextRequest): Set<string> {
  const result = new Set<string>();
  const configured = process.env.APP_PUBLIC_ORIGIN;
  if (configured) result.add(new URL(configured).origin);
  if (process.env.NODE_ENV !== "production") {
    for (const value of (
      process.env.DEV_ALLOWED_ORIGINS ?? request.nextUrl.origin
    ).split(",")) {
      if (value.trim()) result.add(new URL(value.trim()).origin);
    }
  }
  if (!result.size) throw new Error("APP_PUBLIC_ORIGIN is not configured.");
  return result;
}

export function requireSameOrigin(request: NextRequest): void {
  const origin = request.headers.get("origin");
  if (!origin) throw new HttpError(403, "A same-origin request is required.");
  let normalized: string;
  try {
    normalized = new URL(origin).origin;
  } catch {
    throw new HttpError(403, "A same-origin request is required.");
  }
  if (!allowedOrigins(request).has(normalized))
    throw new HttpError(403, "A same-origin request is required.");
}

function rateLimitSalt(): string {
  const salt = process.env.IHEAR_RATE_LIMIT_SALT;
  if (salt) return salt;
  if (process.env.NODE_ENV === "production")
    throw new Error("IHEAR_RATE_LIMIT_SALT is not configured.");
  return "ihear-local-rate-limit-v1";
}

export function requestIpHash(request: NextRequest): Buffer {
  const forwarded = request.headers
    .get("x-forwarded-for")
    ?.split(",")[0]
    ?.trim();
  const address = (
    forwarded ||
    request.headers.get("x-real-ip") ||
    "local"
  ).slice(0, 128);
  return createHmac("sha256", rateLimitSalt())
    .update(`ip:${address}`, "utf8")
    .digest();
}

export function setSessionCookie(
  response: NextResponse,
  request: NextRequest,
  scope: "owner" | "patient",
  token: string,
  expires?: Date,
): void {
  const forwardedProtocol = request.headers
    .get("x-forwarded-proto")
    ?.split(",")[0]
    ?.trim();
  const secure =
    process.env.NODE_ENV === "production" ||
    forwardedProtocol === "https" ||
    request.nextUrl.protocol === "https:";
  response.cookies.set(
    scope === "owner" ? OWNER_COOKIE : PATIENT_COOKIE,
    token,
    {
      httpOnly: true,
      sameSite: "lax",
      secure,
      path: "/",
      expires,
    },
  );
}
